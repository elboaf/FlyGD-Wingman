# Preview label readability — implementation notes

## Coordinator post-review evidence

The following coordinator evidence applies to implementation head `2b805767`
(base `d0a24655`); historical checkpoints below are preserved.

- Coordinator polish `--fix`: zero findings, zero fixes and no code edits.
  Independent general/spec/quality, silent-failure and comment-claim passes
  completed with zero actionable findings.
- Actual CodeRabbit CLI review of `d0a24655..2b805767` completed successfully,
  reviewed all 25 changed files and reported two minor documentation findings.
  This docs-only follow-up addresses both hash-leading paragraph openings;
  CodeRabbit has not reviewed this follow-up commit.
- Fresh coordinator post-polish focused tests: **1,316 passed, 1 skipped in
  35.41s**. The sole skip requires the real Windows pump/window station.
  JUnit: `/tmp/wingman-label-parent-post-polish.xml`. Ruff lint passed, Ruff
  format check passed (431 files), and all-page Node smoke passed.
- Isolated Chromium exercised the actual page with dev-only bridge doubles at
  **840x625** and **839x621** CSS pixels. Geometry/no horizontal overflow,
  keyboard/focus-visible, refusal rollback/retry and tab-return behavior passed,
  with no extra settings reads, no focus theft and zero page errors.
- Windows automated, native/live-EVE, installed-font and DPI acceptance gates
  remain **NOT RUN**. Browser evidence does not replace those gates.

Evidence is retained in the ignored
`.superpowers/sdd/preview-label-readability-plan/` workspace: `progress.md`,
`polish-report.md`, `coderabbit-report.md`, `coderabbit-2b805767.log` and
`browser-results.json`. No full suites were rerun for this prose-only follow-up.
No push, PR creation or issue closure was performed.

## Task 1 implementation checkpoint

**#214 is implemented locally; coordinator review and acceptance are pending.**
The sole persisted addition is global `preview.label_size`: `standard` (17px),
`large` (20px), `extra_large` (23px). Existing `defaults_version` stays 2, and
layouts, hotkeys, crops, alerts, geometry and all other defaults are unchanged.
Issues #215 and #217, per-character appearance and neighboring endpoint cleanup remain
excluded. The supplied approved Spec and plan are preserved.

The shared pure `preview/labelsize.py` table drives validation and rendering;
checked HTML supplies the UI choices/default. The main Settings field owner
serializes the new select's writes, protects newer drafts and rolls refusals
back to its last acknowledgement. Before first hydration, even a focused early
interaction is overwritten with the stored preference because no edit could
have committed. No additional settings read or whole-settings push was added.

`Api.set_preview_label_size` refuses invalid input before the writer, and posts
restyle only after an applied/persisted result (including a valid no-op). The
host reads a retained committed-preview callback, not the tentative document;
its default/invalid/raising fallback is Standard. It passes the key at creation
and assigns it before `set_labels` during restyle. Off does not start a pump.
The acknowledgement means configuration committed, not synchronous native paint.

The existing overlay resolves the font and bounds measurement/rendering by the
owner's interior height. The explicitly approved legacy correction applies to
**every** preset, including Standard: secondary is omitted first, then the whole
pill if primary cannot fit, and content returns when it fits. No glyph cropping,
font auto-shrink or preview/source resizing was added. Cache identity uses the
font and effective layout, not raw dimensions. Same-layout geometry reuses the
bitmap; size changes use the existing overlay and leave chrome/alert/font caches
alone. Existing generic restyle work is unchanged.

### Incremental RED/GREEN evidence

All runs used the linked worktree and
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync`.
Exact commands and logs are in the ignored task report at
`.superpowers/sdd/preview-label-readability-plan/task-1-report.md`.

| Gate | Observed RED | Observed GREEN |
| --- | --- | --- |
| Schema (`test_settings_preview.py -k label_size`) | 13 failed, 52 deselected; missing/dropped key | entire file: 65 passed |
| Renderer (`test_preview_chrome.py`) | 21 failed, 22 passed; missing `max_h` | 43 passed |
| Endpoint/committed callbacks (`-k label_size`) | 19 failed, 202 deselected; missing endpoint/callback | both files: 221 passed |
| Host/window | 50 failed, 412 passed, 1 skipped; missing delivery/font/constructor contracts | expanded runtime selection: 771 passed, 1 skipped |
| Settings runtime + new lexical contracts | 4 pytest failures; 12 new field-owner and 1 new tab case failed, existing JS cases passed | runtime/page/bridge: 257 passed |

The first API GREEN attempt exposed a test-fixture assumption: `make_api` starts
with a minimal legacy document, so direct `save` did not publish normalized
committed defaults. The rollback test now initializes via real `settings.update`
before fault injection; no production workaround. The first off/on RED raised
inside the fake pump and timed out; recording `kwargs.get` moved the assertion
back to pytest (3 explicit missing-key failures), keeping teardown healthy.
Existing explicit renderer doubles now accept/forward `max_h` and assert the
expected budget; their original behavioral assertions remain.

Before renderer edits, three fitting Standard images were captured in
`/tmp/wingman-label-default-before/{0,1,2}.png` for `Pilot` at width 108 with
secondary None, `HOME`, and 60 `W`s. After implementation all three
same-environment byte comparisons returned **True**. Their SHA-256 values were:

- None: `36cf71cb4564177c273520642173bf5a4a17eaf216d3b60f6fde949f3789fc1c`
- HOME: `5b6af3088a3e48b925f25be31dbb7dae658812553490c4cef880ab36b9ebd963`
- long: `97c3a88fc85b57416bab40a0a55b2b7d55a0c2840b37bac677aae82b335bdc5e`

These are Linux-only evidence, not cross-platform test oracles. Tests resolve
all selected primary/secondary sizes to bundled Inter. Pillow tests and fake
native boundaries cover both insets, min/default/legacy geometry, independent
ellipsis, primary-first height thresholds, hide/restore, cache/lifetime, metadata,
Off/on and no source geometry delivery. They do not prove real HWND behavior.

### Fresh engineering gates

Commands run from `/mnt/c/dev/flygd-wingman/.worktrees/preview-label-readability`:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync python -m pytest tests/test_preview_chrome.py tests/test_preview_window.py tests/test_preview_host.py tests/test_preview_wiring.py tests/test_preview_metadata.py tests/test_preview_runtime.py tests/test_settings_preview.py tests/test_settings_committed_preview.py tests/test_settings_runtime.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_settings_page.py tests/test_dev_harness.py -q -rs --basetemp=/tmp/wingman-preview-label-readability-focused --junitxml=/tmp/wingman-preview-label-readability-focused.xml
# 1260 passed, 1 skipped in 34.81s.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync ruff check .
# All checks passed.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync ruff format --check .
# 431 files already formatted.
node scripts/js_smoke.js
# PASS every page module loaded (all three documents).
git diff --check
# Exit 0.
```

Full-suite prerequisites were executed, not inferred from focused tests:

```bash
node --version
# v26.5.0
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target
# Exit 0; release build finished in 5.00s.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available(), 'Native integration tests require the built codec'; print('Installed available release codec:', target.resolve())"
# Exit 0; installed only this checkout's ignored packaging/bin binary.
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
# 1 passed, 0 failed/ignored.
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-preview-label-readability-full-final --junitxml=/tmp/wingman-preview-label-readability-full-final.xml
# 11757 passed, 13 skipped in 311.12s.
```

Release/source and installed codec SHA-256 both:
`4a4b57f48829002be1aff6eda8193f9e1fb8257a9bef5666dd26b0e225e815b4`.
The first full run was **1 failed, 11756 passed, 13 skipped**: the existing exact
`tests/test_settings.py` defaults literal omitted the new key. That directly
related, one-line expected-schema update is the only file-map addition to the
plan. Its entire file then passed (56 tests), and the full suite above was rerun
without further source changes. No unrelated failure was repaired.

All actual full-suite skips are platform-only: profile-copy Windows junctions
(3), DPAPI/WinDLL (2), real preview pump/window station (1), Win32 bindings (3),
pystray Windows backend (1), setup Windows junctions (2), Wanderer user-bound
DPAPI (1). Focused skip is the real pump/window-station case. **No Node or native
codec coverage skipped.** Python tests redirect `LOCALAPPDATA` to temporary state;
only synthetic test data and the checkout-local codec were used.

After the related defaults-literal correction and documentation update, the
focused command above was rerun with `tests/test_settings.py` appended and
`--basetemp=/tmp/wingman-preview-label-readability-final-focused
--junitxml=/tmp/wingman-preview-label-readability-final-focused.xml`:
**1316 passed, 1 skipped in 39.14s**. Ruff check, Ruff format (431 files), JS smoke
and `git diff --check` all passed again in that same final command chain. JUnit
inspection of the final full suite confirmed 11770 cases, zero failures/errors
and exactly the 13 Windows-only skips enumerated above. No source edits followed.

### Pending gates and limitations

- **Mandatory coordinator gates before any PR:** `/polish --fix` **and an actual
  CodeRabbit review**, fixes if needed, fresh post-fix verification and exact
  reviewed SHA evidence. Both are **PENDING / NOT RUN by this worker**. Self-review
  is not CodeRabbit or independent review; no nested reviewers were launched.
- Browser-render at 840×625 / 839×621, Windows automated, installed bundled-font,
  Windows/WebView2, 100/125/150/200% and mixed-monitor native/click-through/source-
  bounds acceptance are **NOT RUN**. New smoke checks retain these separate gates
  without relabeling previous historical statuses.
- The user’s live Windows app, installed binaries, real settings and EVE windows
  were not run or changed. No push, PR, merge or issue edit occurred.
- Self-review checked the final source/test diff against the approved brief:
  no additional schema, defaults-version change, #215 scaffolding, new dependency,
  extra native/cache owner, source geometry call or neighboring endpoint cleanup.
  No known implementation defect remains from that self-review; acceptance is open.

## Planning checkpoint — historical status and boundary

Planning and existing-baseline verification only for **#214**. No production or
test source was edited, and no new-feature test has run. #215 (optional static
per-character markers), #217 and every other backlog feature are excluded.

- Spec read first: `docs/preview-identification-design.md` (maintainer-approved).
- Worktree: `/mnt/c/dev/flygd-wingman/.worktrees/preview-label-readability`.
- Branch: `feature/preview-label-readability`.
- Verified HEAD/base: `d0a24655b36438100076854e9b26243817ed1dd2`.
- Initial status contained only the supplied untracked Spec; it was not changed.
- Environment: Linux; isolated Python environment
  `/tmp/wingman-preview-label-readability-venv`.
- Output: `docs/preview-label-readability-plan.md`; implementation and acceptance
  remain with the coordinator.

## Baseline commands actually run

All commands below ran from the worktree above, before any implementation.

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv sync --locked --extra dev
```

**Exit 0.** CPython 3.11.15; created the isolated environment; resolved 56
packages; built the editable worktree package; installed 39 packages. Included
Pillow 12.3.0, pytest 9.1.1, Ruff 0.16.6 and pywebview 6.2.1. Lockfile unchanged.

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync python -m pytest tests/test_preview_chrome.py tests/test_preview_window.py tests/test_settings_preview.py tests/test_settings_runtime.py tests/test_bridge_contract.py tests/test_page_conventions.py -q -rs --basetemp=/tmp/wingman-preview-label-readability-baseline
```

**Exit 0: `400 passed in 18.89s`; no skips or failures.** This includes both
existing Settings Node runtime harnesses invoked by `test_settings_runtime.py`.
`tests/conftest.py` redirects `LOCALAPPDATA` to each test's temporary state root.
The dedicated basetemp contains only synthetic test artifacts.

```bash
node --version
node scripts/js_smoke.js
```

**Both exit 0.** Node `v26.5.0`; `PASS every page module loaded` for `index.html`,
`fleetbar.html`, and `sigbar.html`.

The release-codec prerequisite recipe was inspected in
`docs/overview-layout-sharing-verification.md#local-verification-prerequisites`.
This focused selection does not run native setup/codec integration and required
no codec build/install. **No full suite, Cargo regression, lint/format,
browser-render, Windows automated, WebView2, frozen-app or live-EVE acceptance
is claimed.** A later full suite must first build/install the release codec in
this checkout's `packaging/bin` and check Node; missing-codec/Node skips are not
acceptable full-suite evidence.

## Read-only geometry/render exercise actually run

This used the existing pure Pillow renderer and layout parser; images stayed in
memory. It did not create an HWND, start Wingman or touch a source window.

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-label-readability-venv uv run --no-sync python -c 'from wingman.preview import chrome, layout; from wingman.preview.window import MIN_SIZE, BORDER; from wingman.preview.alertframes import ALERT_BORDER; import hashlib; print("font_exists", chrome.FONT_PATH.is_file(), "font", chrome._font(17).getname()); print("MIN_SIZE", MIN_SIZE, "insets", (BORDER, ALERT_BORDER)); print("font, inset, available, one_size, two_size, clipped_lines"); [(print(size, inset, (MIN_SIZE[0]-2*inset, MIN_SIZE[1]-2*inset), chrome.label_size("Pilot", MIN_SIZE[0]-2*inset, size), chrome.label_size("Pilot", MIN_SIZE[0]-2*inset, size, "HOME"), chrome.label_layout("W"*60, MIN_SIZE[0]-2*inset, size, "W"*60)[1:])) for size in (17,20,23) for inset in (BORDER,ALERT_BORDER)]; print("legacy", layout.deserialize({"Pilot":{"x":0,"y":0,"w":120,"h":30}})); [(print("legacy_bottom", secondary, inset, inset+chrome.label_size("Pilot",120-2*inset,secondary=secondary)[1], "owner_bottom",30)) for secondary in (None,"HOME") for inset in (BORDER,ALERT_BORDER)]; [(print("default_sha256",repr(secondary),hashlib.sha256(chrome.render_label("Pilot",116,secondary=secondary).tobytes()).hexdigest())) for secondary in (None,"HOME")]; print("font_cache",chrome._font.cache_info())'
```

**Exit 0.** The bundled font exists and loads as `('Inter', 'Regular')`.
`MIN_SIZE == (120, 90)`, `BORDER == 2`, `ALERT_BORDER == 6`.

| Primary / secondary font px | Inset | Available interior | `Pilot` image | `Pilot` + `HOME` image | Independent long-line output (60 W characters each) |
| --- | --- | --- | --- | --- | --- |
| 17 / 14 | 2 | 116×86 | 50×31 | 58×47 | `WWWWW…` / `WWWWWW…` |
| 17 / 14 | 6 | 108×78 | 50×31 | 58×47 | `WWWW…` / `WWWWW…` |
| 20 / 17 | 2 | 116×86 | 57×34 | 67×53 | `WWWW…` / `WWWWW…` |
| 20 / 17 | 6 | 108×78 | 57×34 | 67×53 | `WWW…` / `WWWW…` |
| 23 / 20 | 2 | 116×86 | 63×37 | 76×59 | `WWW…` / `WWWW…` |
| 23 / 20 | 6 | 108×78 | 63×37 | 76×59 | `WWW…` / `WWW…` |

These are Linux Pillow measurements, not proof of native/DPI readability.
The existing formulas give one-line height `font_size + 14` and two-line height
`2 * font_size + 13`. Even 23px leaves 19px below the pill in the smallest
78px-high alert interior. Increasing beyond that buys fewer characters at
minimum width, so the proposal deliberately stops here. The four distinct
font sizes `{14, 17, 20, 23}` fit the existing `_font` LRU capacity of eight;
the probe reported `hits=39, misses=4, maxsize=8, currsize=4`.

### Proposed local preset/schema decision

One global `preview.label_size` string: `standard` (Standard, **17px**, default),
`large` (Large, **20px**), `extra_large` (Extra large, **23px**). Secondary text
keeps the existing primary-minus-three rule, padding, palette and top-left
placement. No per-character field, migration/defaults-version bump, layout
membership, free-form number or additional native resource.

One small pure `wingman/preview/labelsize.py` table holds keys, UI names and font
sizes. Settings, the API boundary and renderer use that table; static HTML
choices/default are checked against it, following the existing checked alert
select pattern. `get_settings()` already carries the nested setting. The only
new endpoint is `set_preview_label_size(value) -> {applied, persisted, error}`.
Malformed stored values fall back to Standard; invalid bridge values are refused
without saving or posting runtime work. This is a proposal, not a shipped schema.

## Existing limitation versus proposed behavior

`window.MIN_SIZE` and the ordinary Settings/drag paths enforce 120×90. However,
`preview/layout.py:deserialize` accepts every positive saved width/height, and
`PreviewHost._resolve_rect` restores those dimensions without enlarging them.
The probe confirmed a 120×30 layout is accepted. With the existing 17px default,
the one-line overlay ends at y=33 (normal) / 37 (alert), and the two-line overlay
ends at y=49 / 53, beyond the owning preview's bottom at y=30. This is **existing
baseline overflow**, not introduced by the preset proposal. The current
`label_layout`/`_sync_label` contract has a width bound but no height bound.

**Material decision for coordinator review before implementation:** the plan
recommends a shared optional height budget in measurement/rendering, supplied
by each owning preview. Keep the full primary line; omit a secondary line that
cannot fit; omit the pill if even the primary line cannot fit. This preserves
current default pixels whenever the existing pill fits, including every
supported 120×90 case, but deliberately changes the already-overflowing default
on undersized restored rectangles. The Spec requires default compatibility as
well as no newly out-of-bounds label pixels; it does not explicitly settle this
legacy-size exception. The coordinator must approve that narrow exception or
request a revision retaining legacy Standard behavior. Do not silently enlarge
previews, clamp saved geometry, crop glyphs, add adaptive font scaling, or resize
any real EVE source to resolve it.

## Coordinator approval after preparation

The coordinator accepted `preview.label_size` keys `standard`, `large`, and
`extra_large` with the measured 17/20/23px mapping and the narrow additive API.
The maintainer then explicitly approved the legacy-size correction: "yes, lets
apply the correction". This resolves the previously open decision above.

Apply height containment to every preset, including Standard: omit the secondary
line when it cannot fit, and hide the entire pill when even the primary line
cannot fit. Restore content when space permits. No preview/source resizing,
automatic font shrinking or glyph cropping. Fitting Standard labels remain
unchanged. The Spec and implementation plan now reflect this approval.

Task 1 is authorized for the coordinator-assigned worker. No implementation or
new-feature verification is claimed by this approval note.

## Other blind spots carried into the plan

- Existing Show labels/opacity endpoints post `restyle()` even after refusal;
  do not copy that behavior into the new endpoint or repair siblings in passing.
- Older standalone Preview listeners do not provide the main Settings IIFE's
  hydration and per-field serialization guarantees. Put the new select inside
  that existing writer, without refactoring the old controls.
- Use `committed_preview` in `build_preview_host`; reading the mutable settings
  candidate could apply a label size whose disk write later rolls back.
- The label cache must include effective layout/text and font size, not raw
  geometry alone. Height changes need a new bitmap only when visible lines
  change. Do not flush chrome/alert/font caches or add a cross-window cache.
- Generic restyle still performs its existing thumbnail/crop/visibility work;
  it must not gain new geometry or lifetime responsibilities for this setting.
- The generic bridge sweep does not recognize the Settings `commit` wrapper.
  The plan includes a focused literal-call/signature assertion for the new
  endpoint, rather than claiming existing sweep coverage or broadening scope.
- Native text visibility, clipping, click-through, DPI and source-window safety
  remain separate Windows acceptance gates. Baseline Python/Node results do
  not establish those outcomes for #214.
