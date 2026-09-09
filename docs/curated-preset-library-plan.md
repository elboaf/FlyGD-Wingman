# Complete Setup Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking. Use named `smart` implementers and independent `review` agents; no nested agents.

**Goal:** Browse bundled complete overview/window arrangements and explicitly import one through Wingman's existing new-profile workflow.

**Architecture:** A read-only catalog module loads bounded metadata and exact existing full `ui-setup` artifacts. Thin facades feed an inline picker owned by `uisetup.js`; existing review/create authorization and publication remain the only application path.

**Tech Stack:** Existing Python, plain HTML/CSS/ES5, pytest, production-module Node harnesses, native settings codec and PyInstaller. No new dependencies.

**Spec:** [curated-preset-library-design.md](curated-preset-library-design.md).

**Status:** library implementation and content packaging are complete through `32cb2d5` (content commit `dc41947`), following the user's approval for continuous implementation. Both exact complete setups are admitted; compatibility prerequisites remain `7783eaf` and `ec41d51`. [Verification](curated-preset-library-verification.md) records reviews, fresh Linux/Windows results and browser evidence. Actual frozen build, installed WebView2/live-EVE acceptance and Windows symlink-privilege test coverage remain open; no release or phase-3 operator acceptance is claimed.

## Global constraints

- Worktree: `/mnt/c/dev/flygd-wingman/.worktrees/curated-preset-library`; branch `feature/curated-preset-library`; base `75f3288e84c80018d6cee421ae2f32577ece53d3`.
- Bundled-only distribution. New releases can change available presets, never previously imported copies.
- Window arrangement is essential. Full `ui-setup` artifacts only; no formation changes or native-only catalog entries.
- Reuse existing strict schemas, parsers, review/controller ownership, manifests, one-shot creation and EVE-closed checks. The user approved the bounded twenty-tab prerequisite below, superseding the previous blanket exclusion; the separately documented DAT corrections preserve existing portable field semantics. No unrelated adapter/schema changes are implicitly authorized.
- Do not search private DATs/captures. Inspect only deliberately designated artifacts. Preserve earlier worktrees and recovery evidence.
- Geometry stays as saved. Recipient resolution/UI scale/preferences remain local. Never move/resize real EVE windows.
- Catalog metadata stays outside artifact envelopes. Text-only rendering. No paths/URLs accepted from callers for artifact loading.
- No new destination, competing controller, generic registry, framework, runtime worker or persisted installed-preset state.
- Source files, tests, docs and configuration changes remain in the linked worktree. No push/PR/build dispatch/install/publication/live-profile work without applicable authorization.
- At least two genuinely useful approved complete setups are an initial acceptance requirement; they may share an overview base but offer distinct arrangements. Missing content is a dependency to report, not permission to declare a single-entry, empty or synthetic-only catalog complete.
- After approval proceed continuously, asking only about material blockers, content permission or external/destructive actions.

## Risk-first decisions covered by the plan

1. **Product:** real complete setups, not redundant formation choices or links to third-party overview YAML.
2. **Content:** user-generated full exports based on third-party overview packs; record license, attribution, author/display context and actual checks. Do not call parser-valid content gameplay-validated.
3. **Authority:** selection only replaces input after an explicit, current Use action. Browsing and read failures cannot invalidate an existing review. Create remains the commit boundary.
4. **Compatibility:** manifest has its own v1; artifact version remains unchanged. Bundle/importer ship together, so no remote min-app-version negotiation or migration is added.
5. **Failure:** malformed catalog refuses locally; manual import remains available. Hash matching detects bundle mistakes, not hostile replacement of both manifest and artifact.
6. **Distribution:** ship assets and license texts through package-data and frozen collection; inspect actual frozen files in the existing build action.

## File ownership

New:
- `wingman/evesettings/setup_catalog.py` — bounded metadata/asset loading, full-artifact parsing, hash matching and summaries.
- `wingman/assets/setup-presets/catalog.json`, full artifact JSONs and license texts — production, reviewed content only.
- `tests/test_setup_catalog.py` — catalog parser/resource behavior and shipped inventory/admission assertions.
- `docs/reference/curated-preset-content.md` — exact provenance, content hashes, author/display context, review and actual validation evidence.
- `docs/curated-preset-library-verification.md` — commands/results and honestly open external checks.

Existing:
- `wingman/paths.py`, `pyproject.toml`, `packaging/uploader.spec` and `.github/actions/build-installer/action.yml` — asset resolution/collection and actual output verification.
- `wingman/evesettings/controller.py`, `wingman/ui/api.py` — read-only wrappers and thin facades.
- `wingman/web/uisetup.js`, `index.html`, `style.css`, `dev.js` — contextual picker; no new route/module/controller. `panel.js` received the narrowly required shared focus-fallback correction exposed by queued replacement.
- `tests/test_ui_setup_controller.py`, `test_ui_setup_page.py`, `fixtures/ui_setup_page.cjs`, `test_ui_setup_integration.py` — exact existing flow, delayed-response and publication regressions.
- `tests/test_bridge_contract.py`, `test_profiles_controller_contract.py`, `test_packaging_completeness.py`, `test_dev_harness.py`, `test_page_conventions.py` — extend established conventions only as needed.
- `README.md`, `docs/smoke-checklist.md`, `THIRD-PARTY-NOTICES.md` — shipped behavior, content acceptance and notices.

## Preparation — isolated baseline

Read the spec and handover; confirm linked worktree identity and clean baseline. If upstream moved, inspect relevant differences before choosing whether to integrate; never overwrite another session's work.

- [x] Create a checkout-specific environment outside NTFS if useful:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv sync --locked --extra dev
node --version
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available()"
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync python -m pytest tests/ -q -rs
```

Record exact baseline and skips. Missing codec/Node is not acceptable coverage. Stop on unexplained baseline failures rather than broadening scope to fix them.

## Prerequisite task — expand the tab budget to the established slot domain

**Status:** implemented after the user's concrete approval on 2026-09-08. Code reviews/polish are complete; the verification record retains the three Windows symlink-privilege failures and unperformed live-EVE checks rather than declaring every gate green.

- [x] TDD for 9/20 tabs, one/eight groups, 21-tab/nine-group refusal, exact assignment/order and required geometry. Keep version 1, eight groups, 32 layout records and other budgets; derive `MAX_TABS` from existing `CLIENT_TAB_SLOTS`.
- [x] Physical slot-19/sparse-to-dense remapping, slot-20 refusal, native twenty-tab one-group application and unchanged recipient geometry.
- [x] Native-codec facade export/review/create/re-export with distinct invented recipients, plus both help areas consuming the new backend limit. No truncation or original-file mutation.
- [x] Separate DAT-only omitted-`alwaysShownStates` correction grounded in current public-client getters. Preserve required fields, strict aliases/present values, canonical guards and portable JSON; test source, effective overrides, affected recipients and nonmutation.
- [x] Separate DAT label projection normalizes exact integer zero to false for bold/italic/underline and underline integer one to true; preserve existing bold/italic integer one, booleans, optional absence and ordered/repeated labels. Current client field reads/formatters establish the effects. Other variants and public JSON remain strict.
- [x] Independent reviews, scoped polish, fresh Linux/Windows gates and replay of both untouched private candidates. Both complete artifacts passed Windows native-codec new-profile/re-export checks on invented recipients. No live EVE profile was changed; this is not library-content approval.

## Task 1 — read-only catalog boundary

**Files:** `setup_catalog.py`, `paths.py`, `test_setup_catalog.py`. Test assets are created under pytest `tmp_path`; this task must not add synthetic production presets.

**Interfaces:** Implement the exact metadata schema and budget rules in the spec. Expose `list_entries()`, `read_entry(preset_id, revision, sha256)`, `SetupCatalogError`, and `paths.setup_presets_dir()`. `read_entry` returns `{entry,text,summary}`. It requires `parsed.source_kind == "wingman"` and `parsed.layout is not None` after the unchanged `parse_text`.

- [x] Write pytest fixtures which copy `tests/fixtures/ui_setup/wingman-preset.json` into a temporary catalog, calculate its SHA-256, write bounded invented metadata/license text and redirect only `paths.setup_presets_dir()` to that directory. Define this fixture in the new test module; it returns `(entry, original_text, directory)`. Use short test IDs and explicit UTF-8.
- [x] Add failing tests for metadata success, exact bytes, derived summaries, no write side effects, duplicate keys/IDs, unknown fields, UTF-8/control/budget bounds, boolean revisions, invalid IDs, absent/link/directory assets, hash/revision mismatch, invalid native-only/probe artifacts and unavailable licenses. Test source and simulated frozen resolver paths. Missing/bad entries cannot fall back to arbitrary local paths.

Example expected public contract (using the fixture described above):

```python
def test_read_returns_exact_full_artifact(catalog_fixture):
    entry, text, directory = catalog_fixture
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    result = setup_catalog.read_entry(
        entry["id"], entry["revision"], entry["sha256"]
    )
    assert result["text"] == text
    assert result["entry"] == entry
    parsed = setup_sharing.parse_text(result["text"])
    assert parsed.source_kind == "wingman"
    assert parsed.layout is not None
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before
```

- [x] Run `python -m pytest tests/test_setup_catalog.py -q` through the checkout environment; record behavioral RED before implementation.
- [x] Implement bounded file reads, shallow manifest validation and strict same-entry/hash loading. Use finite explicit branching, not a registry. Listing reads metadata only; selection parses the artifact. Preserve useful failure context without exposing private filesystem data.
- [x] Run the new tests plus `test_ui_setup_sharing.py`, `test_ui_setup_model.py` and `test_ui_setup_yaml.py`; inspect diff.
- [x] Obtain independent task review, address scoped findings with tests, rerun affected gates, and commit the tested task normally. Never use `--no-verify`.

Task 1 completed in `55f2153` and `e61c8b5`: 839 broader focused passes before the hardlink clarification, 140 catalog/path passes after it, independent SpecCompliance/TaskQuality PASS with an additional 19-case check. No real assets or content-admission claim yet.

## Task 2 — catalog to existing import draft, without new authority

**Status:** complete through `f9636ef`, including independently reviewed queued-dialog visibility/focus corrections, safe diagnostics and the strict Profiles facade inventory. Final Linux: 8,910 passed / 11 Windows-only skips. Windows focused: 2,162 passed / 25 POSIX-only skips / seven symlink-privilege failures. Browser dev scenarios passed at both required viewport sizes. See the verification record; these results do not complete content admission or packaging.

**Files:** controller/API facades; `uisetup.js`, `index.html`, `style.css`, `dev.js`; controller/page/bridge/dev/convention tests.

**Interfaces:** `eve_settings_setup_catalog()` -> `{ok,entries,error}` and `eve_settings_setup_catalog_entry(preset_id,revision,sha256)` -> `{ok,entry,text,summary,error}` as described in the spec. JS owns selection, request identity and provenance display. No new push handlers or persisted state.

- [x] Add controller tests proving reads do not call setup review/create, require EVE to be closed, acquire a mutation lock, save settings or publish events. Success/errors project as documented. Invalid bridge arguments refuse through the module boundary.
- [x] Extend the actual `ui_setup_page.cjs` harness and pytest case list. Required scenarios: list empty/error/retry; exact selected identity sent; literal markup metadata; browse/close preserves existing reviewed input; failed load preserves review; Use requires explicit selection; confirmed replacement clears review/label choice but retains local pair/name; cancelled replacement preserves them; manual text edit clears bundled attribution; read or confirmation delivered after text/name/base/pair change, Close, route exit/re-entry or Create is ignored; pending Paste/File replies after accepted catalog replacement and pending catalog replies after successful Paste/File replacement cannot overwrite text or restore attribution; selection A → B → A cannot readmit A's first response; no automatic Review/Create; detached creation outcomes retain the existing owner.

Representative production-harness assertions (use the fixture's real `click`, `WM` and deferred bridge machinery, adding narrowly scoped catalog reply seams):

```javascript
click('setup-catalog-open');
// Resolve the catalog list through the harness's queued bridge response.
assert.equal(WM.el('setup-text').value, previousText);
assert.equal(WM.el('setup-create').disabled, false,
  'browsing must not invalidate an existing authorized review');
click('setup-catalog-close');
assert.equal(WM.el('setup-text').value, previousText);
assert.equal(WM.el('setup-create').disabled, false);
```

Use stable IDs `setup-catalog-open`, `setup-catalog-close`, `setup-catalog-select`, `setup-catalog-use`, `setup-catalog-details`, `setup-catalog-status`, and `setup-catalog-origin` consistently. The containing region has an explicit `[hidden]` override if its style sets display.

- [x] Run focused new cases and record RED. Implement thin wrappers, inline selector/details/actions and source loading under existing generation/version ownership. Do not reuse `readImport` unchanged: it invalidates review at read start, whereas catalog browsing/failure must not. Invoke `importChanged(true)` only when replacement is accepted and still current.
- [x] Add invented catalog replies only to `dev.js`, inert outside dev mode. Exercise both ordinary and failure/long-data states with the real production module.
- [x] Run `test_ui_setup_controller.py`, `test_ui_setup_page.py`, `test_profiles_page.py`, `test_bridge_contract.py`, `test_page_conventions.py`, `test_dev_harness.py`, and `node scripts/js_smoke.js`; run Ruff and syntax checks on changed JS.
- [x] Independent task review focuses on read-versus-review authority, stale confirmations/replies, input attribution, existing completion ownership and accessibility. Fix/test findings and commit.

Discoveries required narrowly extending `panel.js`'s existing focus fallback and `test_profiles_controller_contract.py`'s exact facade inventory. No new dialog API, queue semantics, public bridge attributes or completion owner were introduced.

## Task 3 — real full setups, provenance, packaging and application evidence

**Status:** on 2026-09-08 the user confirmed both layouts were personally arranged at **3840×2160, 150% EVE UI scale**, approved **FlyGD Wingman** as their layout credit, and identified Z-S as **v10.07.29**. The user subsequently confirmed that the in-game Z-S release provides licence approval for redistribution, answering the GPLv3 applicability question. Admit the designated Z-S capture on that contributor-confirmed evidence, retain the published upstream GPLv3 notice, and do not represent the in-game notice as independently inspected. Author/display/redistribution inputs are now settled; proceed with Task 3. Privacy text review and public filter comparisons are recorded, but are not substitutes for redistribution evidence. Do not add fake metadata, an empty production catalog or copied private snapshots to make packaging appear complete.

**Files:** production assets, content reference, notices, package configuration/build assertions, catalog/packaging/integration tests, README and smoke checklist.

**Consumes:** deliberately selected author exports and confirmed source/display/permission facts. This is a content dependency, not permission to search private evidence. Tasks 1–2 can use synthetic test data while exports arrive; feature acceptance cannot bypass this task.

- [x] Inspect designated full export bytes with existing parser/summary, and record their hashes. Inspect tab/label text for privacy and validate source/redistribution statements. Confirm the advertised window arrangement and intended display context with its author. Do not rewrite, normalize or silently repair the exported bytes. The user nominated Iridium, Signal Cartel, Kisover and Z-S GitLab; the spec records primary-source findings. Prefer Iridium's explicitly licensed current release for the initial derivative. The full upstream v3.11.1 has thirteen tabs; the user's preserved arranged candidate has nine. Do not cut either to eight: the twenty-tab prerequisite accommodates them. Signal Cartel/Kisover need a recorded permission grant; do not treat a public channel as permission. Distinguish Z-S's old GitLab snapshot from current in-game maintenance.
- [x] Write the exact admission evidence to `docs/reference/curated-preset-content.md`; add approved artifacts, catalog metadata, source notices/license text. Obtain at least two approved, distinct complete arrangements, initially using the user's nominated Iridium and Z-S defaults rather than inventing specialised gameplay roles. Do not fabricate a second candidate if only one is approved: report that the content dependency remains open. Candidate role/name is not evidence of suitability.
- [x] Add failing inventory tests which validate every shipped entry, exact hash and full-artifact type; require at least two genuine, distinct complete setups; reject orphaned artifact files. Bind evidence/metadata to the content hash. Guard against production assets importing synthetic fixture names/content. Synthetic negative cases stay temporary.
- [x] Add end-to-end tests that obtain text through the catalog facade and then call the real existing `eve_settings_setup_review` and `eve_settings_setup_create` paths with distinct invented recipient data and the bundled release codec. Assert unchanged base/unselected settings/local display-file bytes, intended groups/ordered labels/layout, single-use publication and refusal paths. Use independent expected content facts; a summary alone is not an application oracle. Existing importer regression suites remain authoritative for their wider cases.
- [x] Test geometry equivalence between the selected artifact and the applied supported records, plus label order/multiplicity. Assert catalog metadata never becomes artifact payload or recipient settings. No formation save or new YAML application path is involved.
- [x] Implement package-data inclusion and explicit PyInstaller `assets/setup-presets` collection. Extend the existing post-freeze build action with a source-versus-frozen manifest/artifact/license byte inventory comparison. Resolve artifact filenames from validated ID/revision; derive inventory, never hand-count it. Exercise missing file and changed-byte failure cases in `test_packaging_completeness.py` using the established build-snippet testing pattern.
- [x] Update README for Browse -> Use -> Review -> Create, as-saved display caveat, source attribution and independent local copies. Extend smoke checklist for usable full-setup selection/import and community content admission rather than a publishing UI.
- [x] Run catalog, packaging, setup controller/page/integration and bridge tests. Independent review covers rights/provenance assertions, real-versus-synthetic data, actual asset inclusion, no hidden importer changes, and expected-versus-derived test oracles. Address findings, rerun, commit.

**Implementation checkpoint:** `dc41947` implements all eight Task 3 checklist items above. Independent SpecCompliance/TaskQuality PASS; scoped failure/comment polish found no actionable issues. TDD: 19 expected initial failures → 19 passes; an added checkout-byte regression failed then passed with scoped Git attributes. Broader focused run: 1,175 passed; fresh affected gate after the attribute change: 228 passed. Final gates: 8,930 Linux passes / 11 Windows-only skips; Windows focused 2,249 passes / 26 skips / seven known privilege failures. Those results preceded the final modal correction below; the corrected final gates supersede them.

**Actual content acceptance — OPEN:** the author/operator uses the complete feature with an independently initialized disposable recipient and checks the saved arrangement, groups/labels and local display preservation. Record actual platform/build/content hashes. Do not use a clone already containing the sender's arrangement as proof of importing it. Further EVE/launcher operations require applicable authorization; engineering results cannot substitute for them.

## Task 4 — polish, independent review and fresh verification

Tasks 1–3 have received scoped polish, independent reviews, full Linux/focused Windows gates and rendered browser checks. The engineering checks below are complete. Whole-branch review found one pending-response modal focus race, fixed in `32cb2d5` with 21 runtime regressions; the scoped rereview returned SpecCompliance/TaskQuality PASS. Corrected final gates: 8,951 Linux passes / 11 Windows-only skips; Windows focused 2,270 passes / 26 skips / seven known symlink-privilege failures. No source changes followed those final gates. Actual frozen/installed/live-EVE acceptance remains separate.

- [x] Render the actual dev module at 840x625 and 839x621: selection/details, long provenance, empty/error, failed reads, replacement confirmation, keyboard/focus, scrolling and pending-read cancellation. Keep isolated browser data; do not access real clipboard or private profiles. Record browser versus Windows evidence separately.
- [x] Run `polish-core --fix` scoped to the feature base. Inspect all edits; do not fix unrelated inherited code. Re-run affected tests after every correction.
- [x] Independent whole-change `review` pass against the approved design; no nested agents. Address findings with focused regressions and scoped rereview.
- [x] Run fresh final gates after the last correction:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync python -m pytest tests/ -q -rs
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync ruff check .
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync ruff format --check .
node scripts/js_smoke.js
node --check wingman/web/uisetup.js
node --check wingman/web/dev.js
node --check tests/fixtures/ui_setup_page.cjs
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
git diff 75f3288e84c80018d6cee421ae2f32577ece53d3..HEAD --check
git diff --check
```

- [x] Inspect skip reasons and actual runtime codec availability. No absent Node/codec skips count as coverage. Inspect final diff for private data, debug output, placeholders, unrelated edits and unsupported success claims.
- [x] Record exact commands/results in the verification document. Use `change-explainer` for completion: what changed, content/source decisions, tests actually run, browser evidence and remaining Windows/frozen/EVE checks.
- [x] Keep branch/worktree available. Seek applicable authorization before push/PR/build dispatch/install/publication or live-profile actions; do not treat plan approval as a release grant.

## Review checkpoints and adaptation

Task reviews are agent work, not user permission milestones. The only expected external inputs are deliberately selected full exports and their authorship/display/rights facts, plus applicable operator acceptance and release authorization. If an artifact violates an existing supported subset, report the specific refusal and choose an eligible artifact or explicitly revisit scope. Never restart schema experiments or silently ship an overview-only substitute.
