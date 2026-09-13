# Preview character markers (issue 215) — implementation notes

## Status and authority

Task 1 is implemented and locally verified against base
`2404917a1eb7771649e9473103f3561bd618cd37`. Final evidence: **12,233 passed / 13
Windows-only skips** in the full Linux suite; **1,837 passed / 1 Windows-pump
skip** in the affected selection; Ruff, format, all-page Node smoke, independent
Cargo and isolated Chromium floor checks passed. The implementation source/tests
were not changed during the documentation-and-commit continuation. The execution
record below distinguishes earlier RED/intermediate runs from final verification.

Authority is the approved issue 215 section of
`docs/preview-identification-design.md`, `docs/preview-character-markers-plan.md`
and the coordinator's Task 1 brief. No product-scope decision changed. Coordinator
`/polish --fix`, independent review and actual CodeRabbit review remain **NOT RUN**
for this change. Windows automation and real Windows/WebView2/native/EVE acceptance
remain **NOT RUN**. A local commit is authorized; no push, PR, merge or issue action
is authorized or performed.

The following discovery/measurement sections retain the earlier planning record;
the **Task 1 execution record** supplies implementation outcomes, adjustments and
remaining acceptance.

Verified clean starting checkout: `/mnt/c/dev/flygd-wingman/.worktrees/preview-character-markers`, branch `feature/preview-character-markers`, HEAD/base `2404917a1eb7771649e9473103f3561bd618cd37` — `docs(previews): address label readability review findings`. No #214 worktree or docs were modified or re-reviewed.

## Current understanding

Provide a static, optional recognition aid inside the existing primary character-name pill. Identity remains the actual name, not its color. Assignment/reset works for known offline owners and remains global, independent of layout geometry, cycle groups, ship data and alert/selection colors. Preserve #214's 17/20/23 global presets and height containment; no new window or appearance editor.

## Confirmed constraints and ownership

- `preview/discovery.py:_character` strips the discovered suffix; stable keys are that exact name. `preview/crops.py:valid_owner` requires an already-stripped, nonempty printable name and excludes `hwnd:`. `preview/roster.py` and most existing per-character maps compare exact keys, not casefolded names. New marker validation will follow the stricter existing crop boundary without changing other features or silently merging identities.
- `settings.py:_preview_defaults` builds fresh nested structures; `validated_preview` rebuilds the section on **every** write. A new map omitted there would disappear on unrelated saves. Use `preview.label_markers: {name: palette_key}`, default `{}`, no migration/default-version bump. Empty/reset values are omitted from persistence.
- `preview/store.py:LayoutStore._protected` protects binds, excluded names, group assignments and crop owners. `roster.touch` can exceed CAP when all entries are protected, but `settings.validated_preview` then caps `seen` at 64. Therefore add marker protection **and** independently retain every valid map entry and union its keys into page rows; do not apply CAP64 to assignments.
- `web/previews.js:rows` already includes group/crop-only owners with null-prototype dedup; `ownValue` protects prototype-like names. Existing marker keys must similarly restore offline rows after normalization/restart. Reset removes only the assignment: existing recent history and other configurations remain. If the marker was the only remaining row source, reset may remove that row just like crop-only removal; existing roster-heading focus fallback applies.
- `ui/api.py:_preview_known_characters` currently serves geometry-copy target validation and omits group/crop-only owners. Do not broaden that unrelated interface. The marker setter's known-source union is live authorized names + committed seen/direct binds/group assignments/crops/markers; layout-only Copy sources do not become new marker targets.
- `settings.update` rolls back failed writes. `_CommittedPreview` publishes detached snapshots only after save; `Api` already retains `_preview_config`. The new setter must return refusal with no restyle after failure. Host reads and the new marker payload fields must use committed authority, not raw in-flight settings. Reuse the label-size endpoint's guarded restyle shape, not older unguarded boolean setters.
- `__main__.py:build_preview_host` already injects committed readers. `PreviewHost._restyle` assigns label size before `set_labels`; marker assignment belongs beside it, and also on primary creation. Existing EVE epoch/admission logic remains unchanged.
- `window.py:_sync_label` caches measured clipped strings, dimensions, font and colors; movement often requires a bitmap push but not rasterization. Marker key/RGB must join only this cache. `_sync_label_visibility` already gates by Show labels, owner visibility and nonempty bitmap. Existing alert frames, border and thumbnail caches are not marker owners.
- `web/previews.js:makeCharacterDetail` is the established Configure-only container, with wrapped fields and no extra collapsed-row columns. `makeGroupSelect`, per-field Settings acknowledgement rules, `detailInteraction`, `rememberDetailFocus`, `requestRender` and tab/section capture cancellation supply the interaction pattern. Do not imitate group replies' whole-table replacement for this scalar field.
- `PRODUCT.md`/`DESIGN.md` require Settings configuration, named accessible controls, preserved actual text, no framework/build step and separate browser/native acceptance. Native palette data lives in one pure module; page choices are derived key/name pairs, not colored text or duplicated hex styles. Thus no web theme/token changes are needed.

## Resolved local proposals (not additional product approvals)

1. **Schema/interface:** `preview.label_markers` holds exact names → palette keys. `Api.set_preview_character_marker(name, marker)` accepts a key or `""` for None, returning `{applied, persisted, error, marker}` with the owner's committed value. JSON null is invalid, avoiding multiple reset meanings. Add `label_markers` and derived `marker_choices` to the existing `get_preview_hotkey_state`/`onPreviewHotkeys` payload; no new handler or round trip.
2. **Retention:** no cap on explicit assignments, consistent with retaining configured crop owners separately from bounded recent history. Forgiving load drops malformed entries only. The live setter refuses unknown owners and invalid values instead of silently normalizing them away. No extra persistent roster, marker history or identity migration.
3. **Rendering:** fixed 8×8 opaque rounded square, radius 2, x=8; 5px gap to primary text. Fixed marker size avoids another per-preset setting. Primary text shifts to x=21, preserving font/text color; secondary stays at x=8. Height is unchanged. Only primary width budget loses 13px. If no original primary glyph fits (including ellipsis-only clipping), omit the whole marked pill. None keeps the prior path, including its existing ellipsis behavior, byte-for-byte.
4. **UI:** a text-only “Identification marker” select inside the currently expanded Configure detail, None first and six named options. Color choices do not need a modal or a new swatch editor. Controls stay editable with previews/labels off or owner offline/excluded. Existing class-based sizing can be shared with the group select through a scoped additional selector; no roster-column or global palette changes.
5. **Acknowledgements:** one in-flight write per owner; disable that select, not every character. Track `{busy, accepted, error, version}` per owner in a null-prototype map and keep successful reset tombstones (`""`) across stale roster pushes. The setter is the sole production writer of this new field, so the page can retain its acknowledged baseline over unrelated discovery payloads, as Settings fields already do. Existing section-entry refreshes can rebase idle owners only if their local submission/settlement version is unchanged since the getter started; this recovers a lost receipt without accepting stale reads over newer writes. Replies patch only their own scalar, never whole hotkey tables. No persisted/server revision protocol, extra getter or general form framework is proposed.

## Geometry and contrast evidence measured here

Measurement artifact: `/tmp/wingman-preview-character-markers-evidence/measure.py`; run against unmodified base source with Pillow 12.3.0 and bundled `wingman/assets/fonts/Inter-Regular.ttf`, confirmed `('Inter', 'Regular')`. This measured **existing** text/layout plus arithmetic for the proposed prefix, not an implemented marker, browser render or native display.

Actual `chrome.LABEL_BG=(10,14,20,235)`, alpha=235/255, is translucent despite a renderer docstring calling the pill opaque. Compositing over black gives `(9.2157,12.9020,18.4314)`; white gives `(29.2157,32.9020,38.4314)`. White is worst-case contrast for these lighter opaque marker colors. Ratios use sRGB linearization (`v/12.92` below 0.04045, otherwise `((v+0.055)/1.055)^2.4`) and WCAG relative luminance weights 0.2126/0.7152/0.0722; unrounded channels used.

| Key / UI name | RGB hex | On black-backed pill | On white-backed pill |
|---|---|---:|---:|
| `cyan` / Cyan | `#56B4E9` | 8.4425:1 | 7.0121:1 |
| `orange` / Orange | `#E69F00` | 8.6494:1 | 7.1839:1 |
| `green` / Green | `#009E73` | 5.6943:1 | 4.7295:1 |
| `purple` / Purple | `#CC79A7` | 6.3641:1 | 5.2859:1 |
| `yellow` / Yellow | `#F0E442` | 14.7322:1 | 12.2362:1 |
| `blue` / Blue | `#0072B2` | 3.7568:1 | 3.1203:1 |

All clear the 3:1 non-text floor against actual background composites. Blue has the smallest margin: retain the exact ≥3:1 automated check and verify visibility manually rather than promising equal salience. Unchanged primary `(235,240,245,255)` measures 14.1115:1 over white-backed pill; secondary `(180,190,205,255)` measures 8.6199:1. A marker is supplementary; no claim that six colors alone provide accessible identity or are mutually distinguishable for every viewer.

`window.MIN_SIZE=(120,90)`, normal inset=2, alert inset=6. Corresponding interiors are 116×86 and 108×78. With existing horizontal padding 8 each side, marked primary budgets are 87px / 79px; secondary retains 100px / 92px. At default 320×210, interiors are 316×206 / 308×198 and marked primary budgets are 287px / 279px.

| Preset | Primary / two-line height | Marker y (8px tall) | `Pilot` measured text width | Long `W` name at minimum, inset 2 / 6 |
|---|---:|---:|---:|---|
| Standard 17 | 31 / 47 | 11 | 34.8594px | `WWWW…` / `WWW…` |
| Large 20 | 34 / 53 | 13 | 41.0156px | `WWW…` / `WWW…` |
| Extra large 23 | 37 / 59 | 14 | 47.1719px | `WWW…` / `WW…` |

Thus the proposed fixed marker has vertical room even in a primary-only pill, and the minimum retains actual primary glyphs at every preset/inset. The marked `Pilot` pill would be 63/70/76px wide (16px padding + 13px prefix + integer text width) without a wider secondary line. For undersized restored heights, retain #214 thresholds exactly: secondary drops below 47/53/59 available px, primary/pill drops below 31/34/37. No glyph crop, font shrink, owner resize or source geometry change.

The measurement also captured **2,430 base-only renderer cases** (dimensions + SHA256 of RGBA bytes) in `/tmp/wingman-preview-character-markers-evidence/base-label-pixels.json`: sizes 17/20/23; widths 0,8,16,20,32,48,108,116,308,316; primary/secondary omissions and legacy height boundaries. This temporary artifact can help compare implementation; durable regression tests must freeze a self-contained base reference, not rely on this file or merely compare two calls to the newly modified renderer.

## Planning baseline actually run in this worktree

All commands below ran from `/mnt/c/dev/flygd-wingman/.worktrees/preview-character-markers`. `node --version` returned `v26.5.0`. No #214 editable environment was reused or repointed.

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv sync --locked --extra dev
```

Succeeded: new dedicated CPython 3.11.15 environment; 56 packages resolved, 39 installed; editable Wingman built from this exact worktree.

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_preview_chrome.py tests/test_preview_window.py tests/test_preview_host.py tests/test_preview_roster.py tests/test_preview_store.py tests/test_settings_preview.py tests/test_settings_committed_preview.py tests/test_preview_wiring.py tests/test_preview_warning_grouping.py tests/test_preview_crops_page.py tests/test_settings_runtime.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_js_smoke.py -q -rs
```

**1,104 passed, 1 skipped in 34.96s.** Sole skip: `tests/test_preview_host.py:1857` — “needs a real message pump and window station”. Node was present; no Node skips. The 10 warning-grouping tests execute real Preview Configure/capture/roster listeners against DOM/bridge doubles; Settings runtime wrappers execute both `test_settings_runtime.js` and `test_settings_tabs_runtime.js`. These are not rendered/browser/native tests.

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_settings.py tests/test_api_settings_fields.py -q -rs
```

**120 passed in 4.61s; no skips.** Combined bounded baseline: **1,224 passed, 1 Windows-pump skip**. No new marker tests exist yet.

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python /tmp/wingman-preview-character-markers-evidence/measure.py
node scripts/js_smoke.js
```

Measurement succeeded with the numbers above. Standalone Node smoke: **PASS every page module loaded**, covering index/fleetbar/sigbar. No codec/full-suite tests were selected, so release-codec setup was not needed. No Ruff, full pytest, Cargo, browser render, Windows automation, WebView2 or live-EVE acceptance was run here.

Coordinator-supplied **#214 evidence only**, not executed here: 1,316 focused passed/1 Windows-pump skip; full worker 11,757 passed/13 Windows-only skips; Ruff/format/Node/Cargo and browser floors passed. Windows/native acceptance remains NOT RUN. Do not transfer these counts into #215 implementation evidence.

## Likely blind spots / critical risks

- **Retention tests need real normalization:** pure `roster.touch` tests alone miss the subsequent CAP64 truncation. Test reload/unrelated writes and a marker-only page row beyond the recent roster.
- **Persistence and page ordering are different:** a discovery push may be sampled before save yet delivered after the receipt. A `pushes` counter alone does not order marker commits. Pin accepted per-owner baselines, version-guarded fresh-read recovery and null/prototype safety with deferred Node tests, without redesigning existing group/crop protocols.
- **None compatibility needs an independent oracle:** measurement and rendering can agree while both regress. Keep base pixel references and reject marker-only/ellipsis-only marked pills at tiny widths without changing the None path.
- **Native usability remains unproven:** an 8px square fits arithmetically; salience, DPI, color perception and exact placement beside text still require authorized Windows observation. Browser floors prove only Configure layout, not Pillow/native label rendering.
- **Existing capture/focus machinery is load-bearing:** adding a field to the detail can interact with crop pushes and replacement renders. Test late replies after Configure/tab/section changes and Copy modal cancellation; no marker callback may steal focus or commit keybinds.
- **Scope/security/deployment:** no external I/O, credentials, new dependency, packaged asset, subpackage or network surface. Validate bridge inputs; text-only DOM assignment prevents names becoming markup. Do not refactor shared palette, identity, lifecycle or saved-layout code while adding this field.

## Decisions that could materially change implementation

No unresolved material product/security/persisted-data decision was found within the approved scope. The schema, exact-name semantics, uncapped explicit assignments, reset returning to ordinary roster-source rules, and fixed shape are concrete local proposals above, not claims of implementation approval. Coordinator review should confirm these before dispatch. Introducing name aliasing, an assignment cap that can discard configured identities, perpetual retention after reset, per-character styling, or a new cross-writer revision protocol would be a design delta and must return to the coordinator rather than being slipped into implementation.

## Coordinator preflight after preparation

The coordinator approved the proposed exact-name map, setter receipt, palette,
fixed marker geometry, uncapped explicit assignment retention and reset following
ordinary roster-source rules. Existing source inspection confirmed that rows
already use exact-name seen/bind/group/crop sources and that screenshot fixtures
have a separate live-state boundary.

Two implementation safeguards were added to the plan:

- None-path evidence must be independent and portable, not Linux-only pixel
  hashes in cross-platform tests or a dependency on a temporary artifact, Git
  checkout metadata or sibling worktree. A small test-local expected-image
  builder with pinned baseline drawing geometry/colors is acceptable; copying
  the entire production renderer or adding another rendering framework is not.
- Existing screenshot fixtures must remain local-only: no real marker writes,
  no contamination of live accepted baselines by fake marker values, and delayed
  real receipts must retain their actual live owner across fixture entry/exit.

These clarify existing compatibility/ownership requirements rather than adding
product scope. Task 1 is authorized for the coordinator-assigned implementer.
Require `/polish --fix`, fresh verification and actual CodeRabbit review before
a #215 PR. Record browser, automated Windows and real Windows/WebView2/live-EVE
acceptance separately; this planning baseline proves none of those.

## Task 1 execution record

### Implementation and self-review

- `preview/labelmarkers.py` owns the approved six-color palette, strict exact-owner
  boundary, forgiving uncapped persisted-map validation and derived None-first
  choices. `settings.py` creates independent maps and preserves them through
  normalization, reload and unrelated writes; reset entries are omitted. Marker
  owners join `LayoutStore._protected` and the page's null-prototype row union.
- `Api.set_preview_character_marker(name, marker)` validates external inputs,
  rechecks committed known sources under the settings writer lock, mutates only
  the owner's entry and returns its committed scalar. Save failures roll back
  RAM/disk and do not restyle. Valid no-ops use `_SettingUnchanged`. Copy's known
  target semantics, lifecycle operations and geometry are untouched.
- The host reads committed assignments at primary creation and once per restyle,
  assigning each key before `set_labels`. Character-select fallback titles get no
  marker. The existing overlay draws the approved opaque 8×8 radius-2 square at
  x=8, with primary x=21 and independent secondary x=8. The label-only cache gains
  marker state; fonts, height thresholds, visibility, native-window count, rings
  and preview/source geometry remain unchanged.
- Configure owns one text-only select and inline error. Per-owner receipt state
  serializes writes, keeps acknowledged values/reset tombstones over stale pushes,
  and permits only version-matching idle getters to recover lost receipts. Empty
  tombstones never source rows. Screenshot fixtures use separate field state;
  real delayed receipts retain their live owner. The dev bridge returns the real
  receipt shape and its choices are checked against Python's palette.
- **Copy Escape correction found during self-review:** the initial marker code
  rebuilt the whole Preview table on submission/receipt. A pending marker receipt
  arriving while Copy's chooser was open detached the chooser's original button;
  Escape consequently could not restore focus to that invoker. The correction is
  confined to the new marker path: `paintMarkerField` updates that scalar control
  in place, rebuilding through `requestRender` only when marker-only row membership
  changes. Existing `panel.js`, Copy methods and dialog lifecycle were not changed.
  The `copy` scenario in `tests/fixtures/preview_labelmarkers.cjs` loads real
  `app.js`, `previews.js` and `panel.js`, opens Copy while a marker write is pending,
  settles the receipt, checks modal focus, then dispatches Escape and checks the
  original attached Copy button. Its RED and GREEN results are recorded below.

### Test-first checkpoints

All commands ran in `/mnt/c/dev/flygd-wingman/.worktrees/preview-character-markers`
with the dedicated environment. RED/GREEN console output is retained in the task
conversation; separate on-disk logs were not created for every incremental run.
These counts are checkpoints, not additional full-suite runs.

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_preview_labelmarkers.py tests/test_settings_preview.py tests/test_preview_store.py -q
# RED: 30 failed, 84 passed in 6.27s — absent model/map and marker-owner eviction.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_preview_labelmarkers.py tests/test_settings_preview.py tests/test_preview_store.py tests/test_settings.py -q
# GREEN: 170 passed in 6.16s.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_preview_wiring.py tests/test_settings_committed_preview.py -k marker -q --tb=short
# RED after fixture correction: 29 failed, 221 deselected in 6.17s — missing setter/callback.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_preview_host.py -k 'marker or label_size_changed_while_eve_off' -q --tb=short
# RED: 5 failed, 358 deselected in 3.02s — missing marker read/creation/restyle.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_preview_chrome.py -k independent_pre_marker -q
# Before renderer edits: 18 passed, 43 deselected in 1.51s against the independent baseline builder.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_preview_chrome.py tests/test_preview_window.py -k 'marker or independent_pre_marker' -q --tb=line
# RED: 289 failed, 12 passed, 175 deselected in 4.48s — missing optional marker parameters.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_preview_labelmarkers_page.py tests/test_bridge_contract.py tests/test_page_conventions.py -k marker -q --tb=short
# RED: 9 failed, 255 deselected in 5.96s — missing Configure control/send contract.
# GREEN, same command: 9 passed, 255 deselected in 5.71s.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_dev_harness.py -k preview_marker -q --tb=short
# RED: 1 failed, 137 deselected in 1.83s — missing dev choices.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_preview_labelmarkers_page.py -k copy -q --tb=short
# RED: 1 failed, 7 deselected in 10.74s — detached Copy invoker after marker receipt.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_preview_labelmarkers_page.py -q --tb=short
# GREEN: 8 passed in 2.47s, including Copy Escape and screenshot isolation.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_preview_labelmarkers_page.py tests/test_dev_harness.py tests/test_preview_window.py tests/test_preview_chrome.py -q --tb=short
# GREEN: 696 passed in 16.09s after expanded secondary/visibility/inset/dev coverage.
```

The illustrative brief assumed `make_api` already had a `preview` section. Its
legacy fixture does not: the first bridge RED run had setup `KeyError` failures
(29 failed / 221 deselected in 5.99s). Tests now establish fresh defaults inside
`settings.update`. Live-owner testing injects `FakeHost.runtime_enabled` explicitly
rather than assuming pump liveness authorizes EVE. Intermediate integration runs
also exposed the not-yet-added host keyword and two narrow chrome-call doubles;
those doubles now accept `marker=None` and assert it without weakening height or
ellipsis assertions. Final verification below covers all bridge/host/render cases.

The None-path oracle is the small test-local `baseline_label_image` builder in
`tests/test_preview_chrome.py`, independently drawing fixed clipped strings with
bundled Inter and pinned pre-marker geometry/colors. It does not copy the renderer's
ellipsis algorithm or depend on Git, a sibling checkout, a temporary file or Linux
hashes. Missing/explicit-None and reset-to-None paths compare against that builder.
The temporary planning artifact was also compared read-only after implementation:
**all 2,430 unmarked cases matched base dimensions and RGBA hashes**. That is
supplemental local evidence, not the portable test oracle; the report records the
exact comparison command.

### Final verification and prerequisites

The dedicated environment was already synced by the planner; no sibling environment
was repointed. Release-codec setup was performed in this worktree before the one full
Linux run, following `docs/overview-layout-sharing-verification.md`:

```bash
node --version
# v26.5.0
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target
# Finished release profile in 5.15s.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; from wingman import paths; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available(), 'Native integration tests require the built codec'; print(paths.codec_exe())"
# Resolved this worktree's packaging/bin/wingman-settings-codec; availability assertion passed.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/ -q -rs --junitxml=/tmp/wingman-preview-character-markers-full.xml
# 12,233 passed, 13 skipped in 316.04s (0:05:16).
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync python -m pytest tests/test_preview_chrome.py tests/test_preview_window.py tests/test_preview_host.py tests/test_preview_roster.py tests/test_preview_store.py tests/test_settings.py tests/test_settings_preview.py tests/test_settings_committed_preview.py tests/test_preview_wiring.py tests/test_preview_warning_grouping.py tests/test_preview_crops_page.py tests/test_settings_runtime.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_js_smoke.py tests/test_dev_harness.py tests/test_api_settings_fields.py tests/test_preview_labelmarkers.py tests/test_preview_labelmarkers_page.py -q -rs --tb=short
# Final affected selection: 1,837 passed, 1 skipped in 48.23s.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync ruff check .
# All checks passed!
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-character-markers-venv uv run --no-sync ruff format --check .
# 434 files already formatted.
node scripts/js_smoke.js
# PASS every page module loaded (index.html, fleetbar.html, sigbar.html).
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
# 1 passed, 0 failed, 0 ignored; independent Cargo regression.
git diff --check
# Passed.
sha256sum packaging/bin/wingman-settings-codec packaging/settings-codec/target/release/wingman-settings-codec
# Both: 4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4
```

The first Ruff check found two new test-local import-spacing errors; targeted
`ruff check --fix tests/test_preview_wiring.py` fixed those, and scoped formatting
preceded final gates. This was ordinary lint/format work, **not** the coordinator's
pending `/polish --fix` review. An earlier affected checkpoint was 1,761 passed /
1 skipped in 45.71s; the final larger selection above includes the subsequent Copy,
secondary-text, visibility, dev-stub and fallback-title coverage.

Full-suite skip reasons, inspected in terminal `-rs` output and retained JUnit:

| Cases | File | Reason |
| ---: | --- | --- |
| 3 | `tests/test_evesettings_profilecopy.py` | requires a real Windows junction |
| 1 | `tests/test_eveskills_dpapi.py` | requires real DPAPI |
| 1 | `tests/test_eveskills_dpapi.py` | requires real WinDLL |
| 1 | `tests/test_preview_host.py` | needs a real message pump and window station |
| 3 | `tests/test_preview_win32.py` | binds user32/gdi32/dwmapi |
| 1 | `tests/test_tray.py` | pystray Windows backend |
| 2 | `tests/test_ui_setup_profile.py` | requires real Windows junction |
| 1 | `tests/test_wanderer_integration.py` | real Windows user-bound DPAPI required |

The affected selection's sole skip is the same real-pump test. No Node or codec
prerequisite skips occurred. JUnit contains 12,246 cases, zero failures/errors and
13 skips; its suite time is 315.900s (pytest's console wall time is 316.04s).
The original XML remains at `/tmp/wingman-preview-character-markers-full.xml`;
continuation copied it byte-for-byte to
`.superpowers/sdd/preview-character-markers-plan/task-1-full.xml` (both SHA-256
`b6f48cec24157494072aaceb120f93e8aaebe30ee31a1733a3183a0c00dff09d`).
No completed suite was rerun solely to regenerate evidence during continuation.

### Browser-only evidence and remaining gates

```bash
node .superpowers/sdd/preview-character-markers-plan/task-1-browser.cjs
# Chrome/153.0.8010.36; four measured states, six screenshots; errors=[], ok=true.
```

The driver launched a **new temporary headless Chromium profile**, served only this
worktree's `index.html?dev=1` on an ephemeral loopback server, blocked non-local page
requests and closed its own browser/server. It did not connect to a user's browser
session, launch Wingman or touch live settings, installed binaries or EVE windows.
At 840×625 and 839×621, populated and offline/excluded Configure each showed all
seven named choices, a live 160px-wide selector at x=385–545, and no page/detail
horizontal overflow (detail client/scroll widths both 605px). Assignment/reset,
held refusal while switching owner, owner-local error retention, and held success
after switching subpage passed. Screenshots `task-1-840-Aiga.png` and
`task-1-839-refusal.png` were opened and inspected.

Artifacts are local/ignored under
`.superpowers/sdd/preview-character-markers-plan/`:
`task-1-browser.cjs`, `task-1-browser-report.json`, and
`task-1-{840,839}-{Aiga,Sera,refusal}.png`. The full task handoff is
`task-1-report.md` in that directory. Browser checks establish Configure rendering
and those interactions only, not native marker salience or Windows focus behavior.

Outstanding: coordinator independent review, `/polish --fix`, actual CodeRabbit
review, hosted Windows automation, Windows/WebView2/native/EVE acceptance, installed
restart and DPI/color-recognition checks. All are **NOT RUN** here. The appended
issue 215 smoke checklist leaves those manual acceptance items open. Blue remains
the lowest-margin palette entry (3.1203:1 over white-backed pill); useful recognition
at typical/minimum native sizes still needs authorized observation. No claims of
mutual color distinguishability, native usability or release acceptance follow from
the automated contrast/containment tests.
