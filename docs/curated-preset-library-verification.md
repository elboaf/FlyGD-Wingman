# Complete setup library — verification record

## Scope and current status

**Current code checkpoint:** `f9636ef09d2ad5d6e1a183b8ca2c9128db37f492`. Library Tasks 1–2 are implemented, reviewed and verified. Task 3 author/display metadata has now been confirmed as recorded below; upstream evidence for Z-S v10.07.29 remains unresolved before content admission. No production catalog or real preset assets are in the repository. The complete-library acceptance floor is not met yet.

**Compatibility-prerequisite checkpoint:** `ec41d514ed3f61ffb2d898453490104be740408c`, after independent final review and scoped polish (no fixes needed). The first sections record the prerequisite needed to export the user's actual full setup candidates; subsequent library task evidence appears below. This does **not** claim that the complete library, bundled content admission, publication, or in-game acceptance is complete.

The user approved a twenty-tab portable budget instead of trimming real overview packs. A separate physical-DAT correction addresses omitted `alwaysShownStates` and exact legacy integer label flags, after read-only current-client inspection established their meaning. Portable JSON remains strict. Private captures are not repository fixtures or approved bundled data.

## Isolation and captures

Worktree: `.worktrees/curated-preset-library`, branch `feature/curated-preset-library`. Base `75f3288e84c80018d6cee421ae2f32577ece53d3`; initial proposal commit `7c151b9581b48121a5c478aaf018f667b8456405`.

At the user's direction, captured the newest already-confirmed pair in the designated Test profile, first for Iridium and later for Z-S. Recency selected between confirmed pairs, never established account ownership. Production setup context/pair validation and the actual Windows closed-state probe were used. Source account/character files and local preference bytes were preserved privately outside the checkout, with SHA-256 receipts and independent verification of all four copied files per candidate. Source files and Wingman settings remained unchanged during each capture. Neither capture was published or included in tests.

Structural observations, without copying personal contents into this record:
- Iridium candidate: nine tabs, three groups (6/2/1). Original export stopped at eight-tab admission. A subsequent replay reached integer-zero label formatting.
- Z-S candidate: six tabs, three groups (4/1/1). Eight saved filter definitions omit `alwaysShownStates`; underline also uses integer one.

The original snapshots remain untouched. Replay uses those snapshots, not whichever setup later occupies the live Test profile. Strict export/reparse and synthetic-recipient application are engineering checks, not proof of EVE rendering or redistribution permission.

## Baseline actually run

Linked checkout, Linux, before source changes:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv sync --locked --extra dev
node --version
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target
cp packaging/settings-codec/target/release/wingman-settings-codec packaging/bin/wingman-settings-codec
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync python -c 'from wingman.evesettings import codec; assert codec.codec_available()'
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-curated-baseline
```

Result: **8,537 passed, 11 skipped in 470.20s**. All eleven skips are Windows-only: three ordinary junction cases, two setup junction cases, DPAPI, WinDLL, one message-pump test and three Win32 binding cases. No native-codec or Node coverage skipped. Node was v26.5.0; locked release codec build/install succeeded.

Windows capture uses a separate locked environment under Windows TEMP, with source imported from this linked checkout. The installed app's codec was copied into ignored worktree `packaging/bin`; source/copy SHA-256 both `18b85ebda93670814f68793e87a971c5d510cd0b0946f226dc6c2ba85c577eef`. This copied a test/runtime dependency, not an installation or build dispatch.

## Twenty-tab task evidence

Commit: `7783eaf4bf436b2a29b8a95e10ab9e6f531398aa` — `feat: support twenty-tab portable setups`.

The limit derives from existing `CLIENT_TAB_SLOTS`. Version 1, eight groups, 32 layout records and all other resource/domain checks remain unchanged. The dev maximum now distributes twenty tabs across eight groups rather than inventing twenty overview windows; production UI help already derives its limits.

Implementer TDD:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync python -m pytest tests/test_ui_setup_model.py tests/test_ui_setup_sharing.py tests/test_ui_setup_yaml.py tests/test_ui_setup_documents.py tests/test_ui_setup_integration.py tests/test_ui_setup_page.py tests/test_dev_harness.py -k 'twenty or sparse_physical or full_twenty or facade_native_yaml or limits_payload or setup_dev_fixture' --tb=short -q
```

- RED: **27 failed, 10 passed, 973 deselected**, from old eight-tab admission/help/dev behavior.
- GREEN: **37 passed, 973 deselected**.
- Broad focused setup/dev suite: **1,478 passed, two Windows-junction skips in 303.18s**; no Node/native skips. An earlier 240-second timeout was superseded by this completed run.
- Ruff lint and format, executable JS smoke, changed-JS syntax and diff checks passed.
- Independent task review: **SpecCompliance PASS, TaskQuality PASS**, no actionable findings. This was read-only code review, not independent test execution.

Parent Windows selected run initially yielded **33 passed, four missing-Node skips**. That result is incomplete coverage and not a final gate. A temporary official Windows Node v24.20.0 LTS runtime was subsequently provisioned outside the repository; its ZIP SHA-256 `6cac9ffbca8f6a47091e4b5c772e0606049c3871cb67d900c0cedde630e545ba` matched the official `SHASUMS256.txt`. No system install or persistent PATH change occurred. Final Windows commands must prepend that directory to PATH.

## Physical adapter and final review

Commit `ec41d514ed3f61ffb2d898453490104be740408c` — `fix: normalize client-proved physical preset representations` — changes only the physical definition and label projections. [Current-client evidence](reference/setup-preset-compatibility.md) records hashes, observed getters/formatters and the semantic boundary without vendoring game code.

TDD selected command:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync python -m pytest tests/test_ui_setup_v24.py tests/test_ui_setup_integration.py -k 'dat_compat or portable_compat' -q --tb=short -rs
```

RED was **21 failed, 113 passed**; final GREEN was **134 passed**. Two new fixture expectations initially confused saved and unsaved filtered-state bodies and were corrected from the existing invented fixture; no extra production behavior change followed. The broader adapter/model/sharing/YAML/integration/codec gate passed **1,142 tests with no skips**. Ruff and diff checks passed.

Independent final review of `7c151b9..ec41d51` returned **SpecCompliance PASS, TaskQuality PASS**, with no actionable findings. It additionally exercised a combined twenty-tab/legacy-representation path in memory, including five strict-portable refusals. That check did not access private captures. Scoped `polish-core --fix` found no safe fixes or outstanding reports: general code review, silent-failure analysis and comment/evidence analysis all returned no findings. No new types were introduced, so a separate type-design analysis was unnecessary. Parent-owned proposal/checkpoint prose was checked separately from the committed code review range.

## Fresh final engineering gates

After all source changes and reviews, the parent ran:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-curated-final-linux --junitxml=/tmp/wingman-curated-final-linux.xml
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync ruff check .
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync ruff format --check .
node scripts/js_smoke.js
node --check wingman/web/dev.js
node --check tests/fixtures/ui_setup_page.cjs
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
git diff 7c151b9..HEAD --check
git diff --check
```

- Linux full suite: **8,704 passed, 11 Windows-only skips in 462.28s**. Same skip categories as baseline; no Node/native skips.
- Ruff lint passed; format check: **331 files already formatted**.
- Executable JS smoke passed all three pages; both explicit syntax checks passed.
- Cargo regression: **one passed**, none failed/ignored.
- Diff checks passed. No production source changed before closing that prerequisite checkpoint; subsequent library changes have their own verification below.

Windows ran from this linked checkout with the locked capture venv, UTF-8 mode and the temporary Node directory prepended to CMD PATH:

```bat
%TEMP%\wingman-curated-capture-venv\Scripts\python.exe -X utf8 -B -m pytest tests/test_ui_setup_controller.py tests/test_ui_setup_documents.py tests/test_ui_setup_integration.py tests/test_ui_setup_model.py tests/test_ui_setup_page.py tests/test_ui_setup_profile.py tests/test_ui_setup_schema.py tests/test_ui_setup_sharing.py tests/test_ui_setup_v24.py tests/test_ui_setup_yaml.py tests/test_dev_harness.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_evesettings_codec.py -q -rs --basetemp=%TEMP%\wingman-curated-final-win --junitxml=%TEMP%\wingman-curated-final-win.xml
```

Windows result: **1,889 passed, 25 skipped, three failed in 208.11s**. The skips are explicitly POSIX-only special-file/unprivileged-symlink and case-sensitive-alias cases. All three failures are `WinError 1314` while the unchanged test fixtures attempt to create symlinks, before the application assertions:

- `test_context_refuses_fallback_or_untrusted_bases[escaped]`
- `test_pairs_require_unambiguous_confirmed_links_and_real_local_files[export-escape]`
- `test_pairs_require_unambiguous_confirmed_links_and_real_local_files[review-escape]`

`tests/test_ui_setup_controller.py` is unchanged by both commits. These are environment-blocked verification cases, **not a passing Windows gate**. No test was suppressed, and Windows Developer Mode, privileges or security policy were not changed. They need a suitably privileged runner or separately authorized environment setup.

The parent independently inspected both JUnit documents. On **each** platform all **19 setup integration cases**, **90 setup-page runtime cases** and **116 dev-harness cases** passed without skips. Node and native-codec coverage is present in the final runs; the earlier missing-Node run is superseded. Neither Node nor Python tests render Windows/WebView2.

## Actual candidate replay

The reviewed production adapter exported both untouched private snapshots through the installed Windows codec, and strict full-artifact reparsing succeeded:

| Candidate | UTF-8 bytes | Filters | Tabs / groups | Ordered labels | Layout records | SHA-256 |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| Iridium-based default | 43,447 | 38 | 9 / 3 | 7 | 12 | `6b212cdc34a8ed8b2a65b53a69e1f4b95d9d1f66abf1e504da18beace24be8a2` |
| Z-S-based default | 62,577 | 57 | 6 / 3 | 7 | 12 | `4c894d18da520457d9622ac4474ae0e08eeaf40574dca1e6cde607b6505e1bb3` |

A separate parent Windows exercise supplied each exact artifact through the existing facade review/create integration harness with **invented recipient files**, actual codec encode/read-back and new-directory publication. It verified exact imported tabs, grouping, ordered labels, settings and layout through re-export, each incoming definition, unchanged original recipient files, preserved recipient identities/non-owned sections and byte-identical local preferences/unselected DATs. Intentional duplicate-Create probes produced the existing consumed-review refusal; no second profile was created. Temporary invented recipients were removed by their owned temporary-directory context. No real EVE profile was targeted.

The candidates and their capture/export receipts remain private under Windows TEMP's `wingman-curated-library-candidates` directory, outside version control. Convenient copies are named `iridium-default.wingman.json` and `zs-default.wingman.json`; their hashes match the table. Raw source snapshots retain all capture hashes. The replay scripts are local verification tools, not a new app entry point or public artifact format. The installed app was not upgraded by these source changes.

## Remaining acceptance and boundaries

- Three Windows symlink-permission cases remain unresolved locally; no fully passing Windows suite is claimed.
- No Windows/WebView2 rendering or actual EVE import/reload of these new candidate artifacts was performed. Earlier phase validation is not relabelled as candidate-specific acceptance.
- Library UI, catalog packaging and approved content/provenance/display metadata remain incomplete under the library plan. Successful export/application engineering checks are not gameplay endorsement or redistribution permission.
- No live-profile edits, real-window movement/resizing, launcher changes, push, PR, hosted build, release, installation or content publication occurred.

### Rulings made during this prerequisite

- Implement the separately approved compatibility prerequisite before the proposed library: this avoids pretending that raw snapshots are already importable content; the cost is a separate prerequisite checkpoint.
- Default only omitted DAT `alwaysShownStates` after the client getter proved its empty-list semantics. If wrong it would change filter meaning; source/recipient tests, strict public input and independent evidence review constrain that risk.
- Normalize only the observed/equivalent exact integer style values at the DAT boundary, retaining existing accepted representations elsewhere. If wrong it would change label appearance; type-sensitive nonmutation, ordered-label and actual native-candidate fidelity checks constrain that risk.

## Library Task 1 — read-only catalog boundary

User approval to execute the remaining library plan is recorded in `44909a3`. The reader/resolver implementation is `55f2153` plus the read-only hardlink clarification `e61c8b5`. No production assets are included by this task.

- Behavioral RED with collection-only scaffolding: **123 failed, 17 existing paths tests passed**; catalog-only RED: **121 failed**. Failures were missing success/refusal behavior, not import/collection errors.
- Initial GREEN: **140 passed** for catalog and paths. Broader catalog/paths/model/sharing/YAML group: **839 passed, no skips**. Scoped Ruff/format/diff checks passed.
- Clarification: read-only package installers may legitimately hardlink resources, unlike live-profile mutation inputs. New acceptance tests failed **three cases** against the initial link-count restriction, then passed after its removal; final catalog/paths group again **140 passed, no skips**. Symlink/reparse/nonregular refusals and exact artifact hashes remain enforced.
- Independent review of `44909a3..e61c8b5`: **SpecCompliance PASS, TaskQuality PASS**, no findings. The reviewer independently ran **19 selected cases**, with no skips, and checked endpoint-file identity and the exact-range diff.

Core focused command:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync python -m pytest tests/test_setup_catalog.py tests/test_paths.py tests/test_ui_setup_sharing.py tests/test_ui_setup_model.py tests/test_ui_setup_yaml.py -q -rs
```

The parent also ran `tests/test_setup_catalog.py tests/test_paths.py -q -rs` with the locked Windows interpreter from the linked checkout. Result: **136 passed, four failed, no skips in 2.65s**. All four failures were `WinError 1314` while creating test symlinks for the three resource kinds and catalog directory, before reader assertions. All three real hardlink cases and ordinary Windows file/resolver cases passed. These four failures join, rather than conceal, the existing local symlink-privilege limitation.

A separate parent Windows exercise created an owned temporary junction with `mklink /J`, supplied it only to `paths.setup_presets_dir`, and verified that listing refused the junction before reading content. Its owned target sentinel remained unchanged; the junction and temporary directory were removed. This passed without any security-policy or privilege changes. It does not substitute for the blocked file-symlink cases or an installed/frozen build.

## Content investigation during library implementation

The parent inspected every exported filter/tab name and label prefix/suffix from both designated artifacts. They contain generic pack labels, public canonical-default names and formatting markup, with no personal names, paths, URLs, credentials or synthetic-fixture markers observed. Only the five expected artifact envelope keys occur. This is a content review, not a redistribution grant.

A read-only membership comparison against Iridium's pinned `releases/iridium_overview_20260728-v3111_main.yaml` at commit `afb001962f5458dee1f21be00c20dc80121ecffb` found **all 38 named filter definitions match** across their three membership lists. Public YAML SHA-256: `0aff208a2df8921845591eaf70cf684faf4da5745ceb00e0bb926b34f228372a`. This supports the filter-source attribution to v3.11.1, not an assertion that the captured tabs, labels or layout equal the upstream YAML. The pinned license explicitly permits MIT or BSD-3-Clause for v2.1+; elect MIT and retain its copyright/notice if this candidate is admitted.

Z-S's captured content does **not** match the linked 2019 edition. Against `Full packs/Z-S Appearance - v9.00.0347 Stylized.yaml` in the pinned April-2019 archive, 55 names are shared: **13 membership matches, 42 differences**; the candidate additionally carries two referenced current canonical defaults. Archive SHA-256: `677a879f743da8bd69b8f0697b717061f55ec53fd24624f85890f95682956cc6`. The archive was read in memory with file/count/byte limits, never executed or extracted into the repository. Those differences do not identify their origin: a different release, local edits or client-side changes remain possible. The old GPL text alone does not establish the captured edition's provenance.

The saved geometry reference is 2560×1440, while copied preferences include a remembered fullscreen scale of 1.5; these alone did not establish the intended mode/resolution. On 2026-09-08 the user explicitly confirmed **3840×2160 and 150% EVE UI scale for both**, said they arranged the windows, and approved **FlyGD Wingman** as the layout credit. The user also identified Z-S as **v10.07.29**. Those facts are recorded from author confirmation, not inferred from geometry. Original overview authors/terms remain separate. Both exact artifact hashes above were reverified after this confirmation; no private artifact or source snapshot has entered version control.

## Follow-up on Z-S provenance

The original author's current [Customizer README](https://github.com/Arziel1992/Z-S-Overview-Customizer/blob/03537e87941296176ace73cda96a60ca78af817a/README.md) identifies **Kismeteer** as the volunteer currently maintaining Z-S. [Kismeteer's public overview page](https://www.wckg.net/home/kisover) confirms that role and directs users to the in-game Z-S version, while linking the original pack repository.

That Customizer bundles a public **v10.06.09** YAML, not the author-reported v10.07.29 capture. A bounded read-only comparison of that YAML (SHA-256 `412541b10959c186dc7958a66fd4362484b72dabce0e3bf12728a57c1aa5f346`) found 39 matching filter memberships after ignoring name markup, 16 differences, and the two referenced canonical defaults absent from that source. This comparison does not change any captured bytes or establish exact edition identity.

The original pack repository declares GPLv3, while the current Customizer declares AGPLv3 for its project. Neither has been substituted for confirmation of the current in-game capture's applicable terms. Its source/licence admission remains open; no maintainer was contacted, no public issue was opened and no assets were admitted. The user-owned layout credit/display facts are settled and must not be requested again.

## Library Task 2 — picker, corrections and scoped polish

Implementation `b9b0b3` added two thin read-only facades and the inline native-control picker. Browsing/failure/cancellation preserve the draft and review. Only a current explicit Use replaces input; it retains local base/pair/name, clears prior review/label choice and records temporary source attribution. Existing Review/Create and Profiles completion ownership remain unchanged. The picker owns separate request state, including serials that defeat A → B → A and cross-source Paste/File races.

TDD initially produced **46 expected failures**, then **46 passes**. Additional real-panel/Create cases exposed three failures and were corrected; dev scenarios added twelve failing cases before implementation. The required focused gate passed **872 tests with no skips**, followed by a fresh **61-case catalog gate**. These were interim results, not the final suite below.

Review and browser findings were corrected rather than waived:

- `9f9d7e6`: prevent cancellation/acceptance from focusing behind the next queued dialog; clear stale selection instructions and bring selected details into the existing scroller only when the user owns select focus. Four expected failures became seven passes; subsequent focused groups passed **403 + 14** tests.
- `0a914f6`: the first full suite found the two new facades missing from the strict Profiles boundary inventory (**one failed, 8,892 passed, 11 platform skips**). Added their names, signatures, delegates, spies and invocation cases without weakening any assertion. The contract file then passed **56 tests**.
- `99fafed`: preserve safe cause-class/OS-code diagnostics for catalog failures. No raw cause text, private paths, body or traceback is logged; UI reply shapes and authority ports are unchanged. **Twelve RED failures → twelve GREEN passes**, then **452 focused passes**.
- `f9636ef`: a final queued acceptance still ended on BODY. Actual Chrome inspection showed the shared panel fallback choosing `us-back` inside the hidden export subview. The panel now checks rendered visibility/enabled state, verifies focus landed, and iterates current-route candidates. No queue-order or public dialog API change. **Three RED failures → eight dialog passes**, then **442 + 26 focused passes**.

Scoped `polish-core --fix` covered `44909a3..9f9d7e6` with general, silent-failure, comment and type/interface roles. No mechanical auto-fixes were needed; the two reported focus/diagnostic issues were verified and corrected with tests. The final bounded independent rereview of `9f9d7e6..f9636ef` returned **SpecCompliance PASS / TaskQuality PASS, no actionable findings**, and independently passed **56 contract, 19 catalog-controller and eight dialog cases**, plus syntax/diff checks. Earlier task reviews establish the rest of Tasks 1–2; this is not an approval of unimplemented content or packaging.

A type reviewer accidentally invoked the default environment instead of the designated `/tmp` environment and could not run pytest. Its type analysis is not test evidence. The parent verified and removed only the newly created empty `.venv`; the actual verification environment and all prior worktrees/captures remained untouched.

## Rendered browser evidence after corrections

Fresh isolated **Chrome 152.0.7977.82**, no copied browser profile, existing CDP sessions untouched. A loopback-only server served this checkout's web directory, and outbound page requests were blocked. Only `dev=1` fixtures were used; the file-picker method was inspected to confirm it was the existing fake, not an OS dialog. No real clipboard, private profile, WebView2 instance or EVE client was accessed.

The parent inspected screenshots and exercised both **840×625** and **839×621** CSS viewports. Two final runs each passed the 13-scenario driver: ordinary selection/use, long literal metadata with wrapping/scrolling/Close, reviewed-input preservation and Escape/confirmation, queued cancellation and acceptance through the final queue drain, empty fallback, list-error/retry, entry-error preservation, delayed A → B → A, Close during a read, and catalog replacement winning over a pending file response. No page exceptions or horizontal overflow were observed in the checked states.

The first screenshot pass showed stale selection guidance and hidden-below-the-fold details; the correction was re-rendered. Final queue-drain focus was verified on **visible Use after cancellation**, **visible Import Cancel after queued acceptance**, and the input after ordinary acceptance. This preserves the shared panel's visible-fallback contract without stealing focus behind an active modal.

Local screenshots/results remain under `/tmp/wingman-catalog-browser-Dmf2S7`; driver `/tmp/wingman-catalog-browser-check.mjs` was run with default widths `839` and `840`. The owned browser/server launcher was stopped after verification; existing sessions were not terminated. These are browser/fixture results, not Windows/WebView2 or gameplay acceptance.

## Fresh final Tasks 1–2 gates

After the last source correction, at `f9636ef`:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-catalog-picker-final-linux --junitxml=/tmp/wingman-catalog-picker-final-linux.xml
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync ruff check .
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync ruff format --check .
node scripts/js_smoke.js
node --check wingman/web/uisetup.js
node --check wingman/web/panel.js
node --check wingman/web/dev.js
node --check tests/fixtures/ui_setup_page.cjs
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
git diff 75f3288e84c80018d6cee421ae2f32577ece53d3..HEAD --check
git diff --check
```

Results: **8,910 passed, 11 Windows-only skips in 455.20s**. Ruff passed; **333 files already formatted**. JS smoke passed all three pages; syntax checks passed. Cargo: **one passed**, no failures/ignored tests. Diff checks passed. No missing Node/native coverage and no source edits followed these gates.

With temporary Node v24.20.0 on CMD PATH, the Windows capture interpreter ran:

```bat
%TEMP%\wingman-curated-capture-venv\Scripts\python.exe -X utf8 -B -m pytest tests/test_setup_catalog.py tests/test_paths.py tests/test_profiles_controller_contract.py tests/test_ui_setup_controller.py tests/test_ui_setup_documents.py tests/test_ui_setup_integration.py tests/test_ui_setup_model.py tests/test_ui_setup_page.py tests/test_ui_setup_profile.py tests/test_ui_setup_schema.py tests/test_ui_setup_sharing.py tests/test_ui_setup_v24.py tests/test_ui_setup_yaml.py tests/test_dev_harness.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_evesettings_codec.py -q -rs --basetemp=%TEMP%\wingman-catalog-picker-final-win --junitxml=%TEMP%\wingman-catalog-picker-final-win.xml
```

Result: **2,162 passed, 25 POSIX-only skips, seven failed in 214.94s**. All seven failures are test symlink creation with `WinError 1314`: the original three controller cases and four new catalog resource/directory cases described above. They occur before application assertions and remain visible; no OS policy or tests were changed to hide them. This is **not** a passing full Windows gate. Actual junction refusal and ordinary/hardlinked resource cases did execute successfully.

The parent inspected both final JUnit documents. Each platform passed all **145 setup-page cases**, **123 dev-harness cases**, **19 setup integration cases**, and **56 Profiles contract cases**, without skips. Final Windows runtime/Node evidence supersedes earlier focused counts; it still does not establish installed/frozen or WebView2 behavior.

## Reviewer focus and current stopping point

Tasks 1–2 are substantial because they add a distribution schema/public read interfaces and integrate asynchronous draft/dialog ownership. The highest-risk decisions are exact identity/byte binding without granting recipient authority, late-source cancellation, and shared focus ownership. The existing independent import/review/create path remains the commit boundary. Task-specific decisions are recorded here and in the SDD task reports/ledger; no unrelated implementation-notes document was used as evidence.

The next work is Task 3, after the remaining upstream terms are confirmed (the user's layout/display facts are settled): admit at least two real full setups, include notices and exact source/display evidence, wire packaging/frozen inventory checks, and exercise the bundled entries through native profile creation. Then repeat whole-feature review and acceptance. No placeholder production catalog, fake display attribution, private snapshots, push, PR, build dispatch, installation or live-EVE operation substitutes for that gate.

### Reviewer knowledge check

1. Why do catalog reads confer no authority to create a recipient profile?
2. Which values bind a selection to the current manifest and exact artifact bytes?
3. Which event invalidates a pending Paste/File response when a catalog replacement wins?
4. Why must focus restoration verify visible targets after the entire dialog queue drains?
5. What remains unproven despite the parser, native-codec, Node and browser results?
