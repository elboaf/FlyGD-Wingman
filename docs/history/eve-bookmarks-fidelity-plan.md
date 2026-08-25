# Restoring AHK fidelity to the EVE bookmarks integration

Follow-up to `eve-bookmarks-plan.md`. The port to Wingman cut more of the
standalone script than "move the GUI" required. The maintainer's intent is
**exact AHK behaviour behind Wingman's GUI**, so most of the cuts are reverted;
the port's genuine bug fixes are not.

## Intended outcome

A user who imports their existing `eve_bookmark_helper.ini` gets the same
behaviour from Wingman that the standalone script gave them, including the
settings and the two bindings the port dropped. New users get a working set of
bindings in one click instead of an empty grid.

## Evidence and constraints

- **Copy/Paste are two lines each.** `eve_bookmarks.ahk:988-995` — `DoCopy:
  Send ^c`, `DoPaste: Send ^v`. There was never a technical obstacle.
- **Copy, Paste and Set Root register globally.** `RefreshHotkeys` Step 4
  registers them under a bare `Hotkey, IfWinActive` with no title; every other
  bind is registered inside `Hotkey, IfWinActive, %WinTitle%` in Step 5. The
  current engine has no global registration at all
  (`engine/eve_bookmarks.ahk:500,513,520,583,608`).
- **`PrefaceReturn` is not Protean-specific and ships enabled.**
  `IniRead, PrefaceReturn, %IniFile%, Settings, PrefaceReturn, 1` (`:116`) with
  preface `!` (`:117`); consumed at `:607-608` and `:1162-1163` as
  `DisplayRoot := ReturnPreface . DisplayRoot`. `eve-bookmarks-design.md:268`
  grouped it with the Protean removal, which the code does not support.
- **`HomeZeroIs0` is likewise mode-independent.** Already established at
  `eve-bookmarks-design.md:30-41`; the engine hardcodes it on
  (`engine/eve_bookmarks.ahk:660-663`).
- **Root Mode is derivable from the existing status field.** `RefreshStatusTab`
  (`engine:158-165`) writes `root` as `""` when `RootModeActive` is false and
  `"(home)"` when the root key is empty. So `Not set` / `Home/Zero` / `Active`
  needs no new engine state — but it would depend on the magic string
  `"(home)"`. See decision 3.
- **The settings schema drops unknown bind ids by construction.**
  `settings.py:72-78` loops over `bookmarks.BIND_IDS`, so adding `Copy`/`Paste`
  to `BIND_IDS` is sufficient for them to survive validation.
- **Import is broken for the real file.** `eve_bookmark_helper.txt` is UTF-16
  LE (BOM `ff fe`); `ui/api.py:1380` reads it as `utf-8-sig`. Every section
  header retains a trailing NUL, fails `endswith("]")` in `_parse_ini`, and
  nothing parses. `import_bookmarks` then saves that empty section over the
  user's settings and returns `{"ok": True}` with no discards and no notes.
  Verified by running the real file through `import_legacy_ini`: one bind set
  (the `ConvertScout` default), zero windows.
- **Conflict flagged, not silently resolved:** `settings.py:35-36` and
  `bookmarks.py` (`DEFAULT_BINDS`) both justify their design by "enabling
  installs a *global* keyboard hook" / "no default global bind means no
  surprise collision". `eve-bookmarks-design.md:54-58` states the opposite —
  that nothing registers globally any more. Decision 1 makes the first comment
  true again, so both must be re-checked rather than left as-is.

## Decisions for review

### 1. Copy, Paste and Set Root register globally (observable behaviour)

Matches the AHK exactly. The cost is real and outside EVE: with the
maintainer's own bindings this makes `^j`, `^k` and `^;` system-wide, and `^k`
shadows VS Code, Slack and browser address bars. Accepted because the stated
principle is exact fidelity, the bindings are opt-in, and reversing one row
later is a one-line change.

**Mitigation, and the one place the GUI deliberately improves on the AHK:** the
three global rows are labelled *works everywhere*, the other eighteen *in EVE
only*. The AHK made this distinction discoverable only by reading
`RefreshHotkeys`.

### 2. `HomeZeroIs0` becomes a setting, defaulting to `.1`

The script's compiled default is `.0` (`:32`). Wingman will default to `.1`.
This deviates from the AHK for **fresh installs only** — any user importing an
existing INI gets whatever their file says, so nobody is silently renumbered.
Maintainer decision.

### 3. Root Mode: add an explicit `root_mode` status field

Deriving it from `root == "(home)"` needs no engine change but couples the UI
to a display string that exists to be shown to humans. An explicit field is one
line in `RefreshStatusTab` and one in `EngineStatus`. Chosen for that reason.

Ordering note: `hotkeys.py:270-321` treats *any* malformed field as `stale`. A
new field must therefore be tolerant of absence — an engine binary older than
the Python side must not push the whole status to `stale`. Default it to `""`
and derive `Not set` from that.

### 4. Restoring settings deletes the discard machinery (interfaces)

`_REMOVED_SETTINGS`, `_REMOVED_BINDS`, the `discarded` list and the renumbering
note in `import_legacy_ini` exist only because of the cuts. With `Mode` the
only remaining removal, import becomes a straight translation plus one note
about Protean. `alert_import` keeps its purpose for that single case.

### 5. `generate_ini` gains a `[Settings]` section

Currently emits `[Keybinds]` and `[Enabled]` only. The same reasoning that
makes it emit blank binds applies: every setting must be written on every
pass, or a missing key lets `IniRead` fall back to the engine's compiled
default and silently resurrect a value the user changed.

### 6. Compatibility

- Existing Wingman settings files have no `home_zero`/`preface_*` keys.
  `validated_eve` supplies defaults, so old files load unchanged.
- Existing files have no `Copy`/`Paste` binds; `DEFAULT_BINDS` gives them
  blank, matching the AHK's own default.
- `settings.py:76-78` claims a stale `Copy` "cannot survive into the generated
  INI". That comment becomes false and must be removed with the change.

### 7. Security and failure handling

- `ReturnPreface` is free text landing in an INI the engine parses. It must go
  through `sanitise()` like the Set Root argument, and be length-capped — it is
  a preface character, not a string.
- The import fix must **not** save on a parse that yields nothing. Reading a
  file and finding no sections is a failure, not an empty config.

### 8. Testing

Everything except the engine itself is testable on Linux, which is where the
coverage has to come from (`bookmarks.py` docstring). The engine changes —
global registration, the settings reads, the new status field — are not
testable and go on the smoke checklist.

## Alternatives and tradeoffs

| Decision | Chosen | Rejected |
|---|---|---|
| Bind scope | Global, as the AHK | Window-scoping all 21 — safer outside EVE, but a deliberate deviation, and breaks the copy-in-EVE/paste-in-Discord half of the workflow |
| `HomeZeroIs0` | Setting, default `.1` | Hardcoding `.1` — one line, but silently renumbers every user whose INI says `1` or omits it, i.e. the script's own default |
| Root Mode | Explicit status field | Deriving from `root == "(home)"` — no engine change, but couples UI logic to a human-facing string |
| Bind defaults | Blank + explicit "Reset defaults" button | Shipping the corp preset as `DEFAULT_BINDS` — imposes one corp's preferences and reapplies silently whenever the section is recreated |
| Preset source | Dict in `bookmarks.py` | Shipping an INI through `import_legacy_ini` — reuses one code path, but the real file's `[Enabled]` section carries character names |

## Ordered implementation steps

1. **`bookmarks.py`** — add `Copy`/`Paste` to `BIND_IDS`, `BIND_LABELS` and
   `DEFAULT_BINDS` (blank); add `GLOBAL_BIND_IDS = ("Copy", "Paste",
   "SetRoot")`; add `RECOMMENDED_BINDS` (the corp preset, `ConvertScout`
   staying `^+s`); extend `generate_ini` with `[Settings]`; strip
   `_REMOVED_SETTINGS`, `_REMOVED_BINDS` and the renumbering note from
   `import_legacy_ini`, and import the two settings instead.
2. **`settings.py`** — add `home_zero` (default `False`), `preface_return`
   (default `True`) and `return_preface` (default `"!"`) to `_eve_defaults`;
   validate them in `validated_eve` with the same strictness as `enabled`;
   delete the now-false `Copy` comment at `:76-78`; revisit the "global
   keyboard hook" comment at `:35-36` in light of decision 1.
3. **Engine** (`engine/eve_bookmarks.ahk`) — restore `DoCopy`/`DoPaste`;
   restore the Step 4 global block for Copy, Paste and Set Root, and remove
   those three from the Step 5 per-window loop; `IniRead` the three settings;
   restore the `HomeZeroIs0` condition in `FireRootFinisher` and the
   `PrefaceReturn` branches at the two `DisplayRoot` sites; add `root_mode` to
   the status JSON. **Preserve the teardown fix** — the restored global binds
   must still be torn down in the context they were registered in.
4. **`hotkeys.py`** — add `root_mode` to `EngineStatus`, tolerant of absence.
5. **`ui/api.py`** — fix the import encoding (sniff the BOM: UTF-16 LE/BE,
   UTF-8 with BOM, else UTF-8); refuse to save a parse with no sections; add
   `reset_binds`; surface `root_mode` and `GLOBAL_BIND_IDS` from
   `get_bookmarks`.
6. **UI** (`web/index.html`, `web/bookmarks.js`, `web/style.css`) — Root Mode
   readout; `HomeZeroIs0` and `PrefaceReturn` checkboxes plus the
   `ReturnPreface` field; "Reset defaults" button; Windows "Refresh" button;
   scope markers on the bind rows.
7. **Tests** — see below.
8. **Docs** — update `eve-bookmarks-design.md` "Scope reductions" to record
   what was reverted and why; add the engine changes to
   `docs/smoke-checklist.md`.

## Testing and verification strategy

New/changed, all Linux-testable:

- `test_bookmarks_import.py` — **the regression that would have caught this**:
  the real UTF-16 LE file imports its bindings. Plus UTF-16 BE, UTF-8+BOM and
  plain UTF-8; a no-sections parse reports failure and does not save.
- `test_bookmarks_ini.py` — `[Settings]` is emitted on every pass including
  when values are at their defaults; `ReturnPreface` is sanitised.
- `test_settings_eve.py` — the three new fields round-trip; an old file with
  none of them loads at defaults; a hand-edited non-bool is rejected.
- `test_bookmarks_keys.py` / `test_bookmarks_validate.py` — `Copy`/`Paste`
  participate in collision detection.
- `test_api_bookmarks.py` — `reset_binds` overwrites all 21; `root_mode`
  reaches the payload; a status without `root_mode` does not become `stale`.
- `test_engine_invariants.py` — pin that Copy, Paste and Set Root are
  registered in the global block and absent from the per-window loop, and that
  the teardown fix still covers them.

Then the full suite, plus `docs/smoke-checklist.md` on Windows for the engine
changes, which no test can reach.

## Adaptation points

- **If `^k` (or another global) proves unusable in practice**, decision 1 flips
  for that row only — no architecture change.
- **If the restored `PrefaceReturn` branches turn out to be entangled with the
  removed Protean code**, stop and re-scope: the Protean removal threaded
  through the finishers and the parser, and `:1162` sits in that region.
- **If `RECOMMENDED_BINDS` collides with EVE's own defaults** (`^1`-`^6` are
  the ones to check on the smoke pass), the preset changes, not the mechanism.

## Explicit exclusions

- Protean/v21 mode stays removed — maintainer decision, unchanged.
- The tray menu stays removed; Wingman's chrome replaces it.
- Sig / Root / Next stay in the global status bar rather than returning to the
  route.
- The port's bug fixes are **not** reverted for fidelity: window-scoped hotkey
  teardown, collision detection (the AHK ignores `ErrorLevel` on every
  `Hotkey` call), and the import encoding.
- The inert `[Custom]` section in the legacy INI. No version of the script
  reads it; it is ignored, not imported.
