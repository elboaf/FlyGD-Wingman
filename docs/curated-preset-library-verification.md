# Complete setup library — verification record

## Scope and current status

**Current code/content checkpoint:** `32cb2d57bd74627f0e38056937e83f8f5d598fdc` (content bundled in `dc41947`). Library Tasks 1–3 are implemented with both admitted complete setups, source/frozen collection and regression tests. The content dependency is resolved using contributor-confirmed author/display/in-game redistribution evidence; the in-game licence notice has not been independently inspected. Engineering verification is recorded below. Actual frozen build, installed WebView2/live-EVE acceptance and the Windows privilege-blocked cases remain open; no release/operator acceptance is claimed.

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

The original pack repository declares GPLv3, while the current Customizer declares AGPLv3 for its project. Neither has been substituted for confirmation of the current in-game capture's applicable terms. Subsequently, the user clarified that the in-game v10.07.29 release provides licence approval for redistribution, answering the GPLv3 applicability question. This resolves admission on **contributor-confirmed in-game notice evidence**, with the published upstream GPLv3 notice retained; it is not an independent inspection or verbatim quotation of the in-game notice. No maintainer was contacted or public issue opened. The layout/display/permission inputs are settled and must not be requested again.

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

Task 3 is now implemented as recorded below: both complete setups, exact notices/provenance, source/frozen collection and native facade application coverage. Remaining acceptance requires a suitably authorized Windows build/install/operator pass, not more schema experiments or a placeholder catalog. No push, PR, build dispatch, installation, real-profile mutation or live-EVE operation has been performed.

## Task 3 — admitted content and distribution

`dc41947` adds the exact Iridium and Z-S artifacts under `wingman/assets/setup-presets`, catalog metadata, MIT/GPL notices, [content admission reference](reference/curated-preset-content.md), package-data/PyInstaller collection, post-freeze byte-inventory verification and user/smoke documentation. Original overview authors remain separate from FlyGD Wingman layout credit. No importer/schema/controller/UI source changed in this task.

The actual build-action snippet derives manifest/artifact/licence inventory from validated catalog identities and compares source bytes with `_internal/assets/setup-presets`. Tests execute it with missing/changed/extra files. Scoped `.gitattributes` disables newline conversion on hash-bound assets; licence notices retain upstream whitespace verbatim. This safeguard was discovered during implementation and does not weaken validation or broad repository whitespace checks.

TDD: **19 expected failures → 19 passes**; an additional checkout-attribute test failed before the safeguard and passed after it. Broader selected tests: **1,175 passed** (a prior timed-out attempt is not counted); fresh affected catalog/packaging/integration files after the attribute correction: **228 passed**. These are separate runs, not an invented aggregate.

Independent Task 3 review returned **SpecCompliance PASS / TaskQuality PASS**, no actionable findings. It independently checked approved byte counts/hashes, committed resource equality, parser reads and GPL notice suffix. Scoped polish in fix mode found no safe fixes or remaining findings: failure analysis independently passed 40 focused cases and eight shell-exit scenarios; comment/evidence analysis passed 17 focused cases. No new types/interfaces required a separate type-design pass. Earlier prerequisite and Tasks 1–2 polish remains applicable; Task 3 added data, tests and packaging rather than changing those runtime contracts.

## Fresh whole-library gates at dc41947

The final Linux command used the existing environment:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/wingman-curated-library-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-library-final-linux --junitxml=/tmp/wingman-library-final-linux.xml
```

Result: **8,930 passed, 11 Windows-only skips in 573.23s**. Then Ruff check passed, Ruff format reported **333 files already formatted**, all three pages passed `node scripts/js_smoke.js`, explicit Node syntax checks passed for `uisetup.js`, `panel.js`, `dev.js` and `tests/fixtures/ui_setup_page.cjs`, and `cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml` passed **one test**, with none failed/ignored. Both branch and unstaged diff checks passed. No missing Node/native-codec coverage.

With temporary Node v24.20.0 on CMD PATH, the Windows capture interpreter ran:

```bat
%TEMP%\wingman-curated-capture-venv\Scripts\python.exe -X utf8 -B -m pytest tests/test_setup_catalog.py tests/test_paths.py tests/test_packaging_completeness.py tests/test_profiles_controller_contract.py tests/test_ui_setup_controller.py tests/test_ui_setup_documents.py tests/test_ui_setup_integration.py tests/test_ui_setup_model.py tests/test_ui_setup_page.py tests/test_ui_setup_profile.py tests/test_ui_setup_schema.py tests/test_ui_setup_sharing.py tests/test_ui_setup_v24.py tests/test_ui_setup_yaml.py tests/test_dev_harness.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_evesettings_codec.py -q -rs --basetemp=%TEMP%\wingman-library-final-win --junitxml=%TEMP%\wingman-library-final-win.xml
```

Result: **2,249 passed, 26 skipped, seven failed in 275.89s**. The seven failures remain `WinError 1314` during test symlink creation, before application assertions: four catalog cases plus three existing controller cases. The 26 skips are 25 existing POSIX-only cases and one **pre-existing** manual-update-harness symlink-unavailable skip brought into this selection by the packaging test module. No new skip or privilege workaround was introduced. This remains a partially blocked Windows gate, not full-green Windows verification.

The parent independently inspected both final JUnit files: **23 integration**, **145 setup-page**, **123 dev-harness** and **56 Profiles contract** cases all passed without skips on each platform. The matching catalog/inventory selection likewise had no failures/skips. Both real bundled presets passed native facade review/create and stale-recipient refusal on each OS.

## Final rendered catalog checks

A new isolated Chrome **152.0.7977.82** session, loopback-only web server, fresh browser profile and blocked outbound page requests repeated the 13-scenario dev driver at each default viewport (839×621 and 840×625); both runs passed. Final real-catalog checks took the exact production `setup_catalog` reader results and supplied them to the **fake dev bridge**, exercising both entries at both viewports: **four passes**. Assertions covered metadata rendering/no horizontal overflow, explicit Use, exact textarea SHA-256, origin attribution, visible input focus, and no automatic Review/Create. Screenshots were inspected after the final count-free descriptions landed.

These real-content browser checks are not a Python/WebView2 bridge test: native facade tests provide the separate backend evidence. No real clipboard, file picker, private browser profile or EVE instance was used. Evidence remains at `/tmp/wingman-catalog-browser-2Drr4u`; drivers `/tmp/wingman-catalog-browser-check.mjs` and `/tmp/wingman-bundled-catalog-browser-check.mjs`. No page exceptions were recorded. The owned browser/server was stopped; existing browser sessions were untouched.

The parent also compared every committed asset with its working-tree bytes and verified both original approved artifact hashes. Actual wheel/PyInstaller output, installed WebView2 and live-EVE rendering remain **unperformed**. The newly added build gate will verify actual frozen bytes when an authorized build is run; executing its tests does not substitute for that build.

## Final whole-change review and modal correction

The independent whole-branch review of `75f3288..dc41947` found one P2: a pending Paste/File or Review response could focus or scroll the background page while the catalog replacement confirmation was open. Stale-input/recipient authority guards held; this was keyboard/modal ownership, not an unauthorized-write finding. The parent reproduced Paste stealing focus in actual Chrome with a fake clipboard before the fix.

`32cb2d5` guards those response focus/scroll actions and the analogous attached Create-completion focus. Valid response state and authorization processing still occur; no deferred focus retry or queue API was added. Only `uisetup.js` and its page tests/harness changed. **18 expected failures / three existing passes → 21 passing new real-panel cases**, then **956 broader focused passes**, no skips. Cases cover Paste/File, Review summary/label choice, successful/failed attached completion and final dialog-queue focus/action validity.

Scoped independent rereview returned **ADDRESSED, SpecCompliance PASS / TaskQuality PASS**, carrying forward the whole-change review whose sole finding was this P2. It independently ran all **21** new cases successfully. There are no outstanding findings. Parent inspection found no further safe polish edits; the correction adds no types and preserves prior reviewed ownership contracts.

### Corrected final gates — supersede the dc41947 counts above

At `32cb2d5`, reran the same full Linux command and complete Windows module selection above, changing only output locations from `wingman-library-final-*` to `wingman-library-corrected-*`:

- **Linux: 8,951 passed, 11 Windows-only skips in 635.34s.** JUnit `/tmp/wingman-library-corrected-linux.xml`.
- **Windows focused: 2,270 passed, 26 skipped, seven failed in 284.78s.** JUnit `%TEMP%/wingman-library-corrected-win.xml`. Failures/skips have the same causes described above; no tests or OS privileges were changed to suppress them.
- Ruff check passed; format check **333 files already formatted**. Three-page JS smoke and four explicit syntax checks passed. Cargo **one passed**, no failures/ignored tests. Branch/working diff checks passed.
- Both JUnit files independently checked: **23 integration**, **166 setup-page**, **123 dev-harness**, **56 Profiles contract** cases all passed without skips on each platform. No absent Node/native coverage.

The final isolated Chrome session at `/tmp/wingman-catalog-browser-fxu8Qz` passed all four newly reproduced delayed-response branches (Paste, File, Review summary, Review label choice): focus remained on Confirm and the background scroller stayed put; queue drain restored visible Use. It also passed both exact bundled entries at both viewports (**four real-content cases**) and reran the existing **13-scenario dev driver twice**, at default 839×621 and 840×625. No page exceptions were recorded. These remain fixture-bridge/browser checks, not WebView2/live-EVE acceptance. The owned browser/server was stopped afterward, preserving artifacts and unrelated sessions.

No source or content changes followed these corrected final gates; only status/verification documentation was updated. Remaining work is an authorized actual Windows build/install/operator acceptance pass and suitable-runner coverage for the privilege-blocked tests. No source/capture rewrites, push/PR, publication, installation, upstream contact, launcher or real-profile action occurred.

### Reviewer knowledge check

1. Why do catalog reads confer no authority to create a recipient profile?
2. Which values bind a selection to the current manifest and exact artifact bytes?
3. Which event invalidates a pending Paste/File response when a catalog replacement wins?
4. Why must focus restoration verify visible targets after the entire dialog queue drains?
5. What remains unproven despite the parser, native-codec, Node and browser results?
