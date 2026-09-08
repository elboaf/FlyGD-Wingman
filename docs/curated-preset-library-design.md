# Curated library of complete overview and layout setups

Status: the user approved library implementation on 2026-09-08, with continuous execution and independent reviews. The compatibility prerequisite is implemented and verified as recorded in [the checkpoint](curated-preset-library-verification.md). Content admission and external/operator acceptance remain separate requirements.
Base: `75f3288e84c80018d6cee421ae2f32577ece53d3` (current main when the planning worktree was created).

## Outcome and decisions

Wingman helps players choose a useful **complete overview and supported window arrangement**, then explicitly create a new local profile from it. Merely redistributing overview YAML adds little over existing third-party sources. Repackaging Wingman's built-in formation templates also adds little. Neither is this phase's product.

Decisions established with the user:

- Bundled-only distribution. No catalog server, downloads, refresh, cache or background synchronization. New releases can change available presets, never previously imported copies.
- Initial content consists of full `wingman-preset` / `ui-setup` version-1 artifacts. Saved window arrangement is essential. Native YAML remains available through the existing manual import path, not as a library substitute for a complete setup.
- Build a small set from established third-party overviews plus deliberately created and validated window arrangements. The user will generate some complete exports now; nominated roles are scanning/exploration and fleet/combat. They may share an overview base. Roles are editorial descriptions, not a new schema or automation feature.
- Community-generated complete artifacts can follow through the same maintainer review and release process. This does not authorize a submission portal, moderation service, account system, or private-corporation access.
- Existing formation selection and sharing remain untouched.

The user rejected an earlier formations-first seed and an overview-only catalog. Those proposals are superseded; do not implement them or ship an empty library as the phase's outcome.

## Evidence and constraints

- `docs/settings-sharing-design.md`, Outcome and roadmap: the high-value goal is a complete ready-to-fly setup; libraries distribute explicit local copies.
- `docs/overview-layout-sharing-design.md`: full artifact, recipient-local construction, as-saved geometry, ordered labels, stack refusals and one-shot new-profile creation contracts.
- Both earlier sharing phases are validated and merged. Historical OPEN checkpoints are not new schema investigations or unfinished implementation.
- `wingman/evesettings/setup_sharing.py:parse_text` and `setup_model.py:summarize`: artifact-only parsing and summaries do not require recipient authorization. A full setup is strict; catalog metadata cannot enter its envelope.
- `wingman/evesettings/controller.py:setup_review`, `setup_create`: the existing controller owns review authorization, mutation locking, full manifest checks, EVE-closed checks and publication. Pure catalog browsing must not call `setup_review`.
- `wingman/web/uisetup.js:importChanged`, `readImport`, `editable`: replacing text invalidates an old review and label-retention choice; pending I/O needs view/version correlation. Sent Create receipts outlive private input.
- `wingman/web/evesettings.js` is the sole completion-event owner. No additional owner or route is needed.
- Main's #185 formation account-label and Profiles recovery changes are inherited and preserved. No edits to their behavior are planned.
- `PRODUCT.md` and `DESIGN.md`: plain HTML/CSS/ES5, existing dark theme/tokens, 840x625 CSS floor (also stress 839x621), explicit local actions and no real EVE-window movement/resizing.

## Content and provenance

### Acquisition

Use the existing **Share setup** workflow to produce full artifacts after the author has arranged a setup in EVE. Do not convert native YAML into a purported complete layout by borrowing recipient geometry or inventing coordinates. Do not automate EVE or create profiles during development without applicable authorization.

Only deliberately designated exports are eligible for inspection. Never search private DATs, old recovery captures or personal folders for content. Original exports can remain outside version control until reviewed. User-authored tab names and ship-label text are not anonymous merely because the exporter excludes identities.

For each candidate, record:

- Third-party overview origin, author/attribution, exact source version or commit and redistribution terms.
- Layout author, a plain-language purpose and intended display context (width, height, UI scale), supplied/confirmed by the author rather than inferred from geometry reference sizes.
- Exact artifact bytes and SHA-256, plus a stable library ID and integer revision.
- Technical and actual EVE verification evidence, keeping each distinct. The library must not imply fleet approval, universal display compatibility or current-client testing that did not occur.

The user nominated these sources; investigation is source selection, not approval of their content for Wingman:

| Source | Evidence checked | Admission consequence |
| --- | --- | --- |
| [Iridium](https://github.com/iridiumops/overview) | `license.md` explicitly licenses v2.1.0 onward under MIT OR BSD-3-Clause. Latest API release was v3.11.1 (2026-07-28); source inspected at `afb001962f5458dee1f21be00c20dc80121ecffb`. Its main YAML has 13 tab records and 38 definitions. | Strongest first base; elect MIT and carry the copyright/permission notice. The user rejects trimming to Wingman's old eight-tab budget; the bounded twenty-tab prerequisite below supersedes that earlier recommendation. |
| [Signal Cartel / Explorer's Overview](https://wiki.signalcartel.space/Public:Signal_Cartel_Overview_Pack) | Public page describes exploration-first presets, current maintainer Echerie Saissore, 2026 changelog updates and in-game distribution through Explorer's Overview. No explicit artifact redistribution license was found in the fetched page. | Good exploration candidate; obtain a clear redistribution grant before bundling. A public channel or wiki-content license is not automatically an artifact license. |
| [Kisover](https://www.wckg.net/home/kisover) | Author describes a maintained in-game pack, fleet-role filters and multi-window arrangements. No explicit artifact redistribution license or downloadable versioned artifact was found in the fetched page. | Candidate after permission and exact in-game source/export identity are recorded. Do not infer multi-window behavior or authority from screenshots alone. |
| [Z-S GitLab](https://gitlab.com/Arziel/Z-S-Overview-Pack/) | Project API identifies `master`; latest branch commit `594b37af9f91714ed7f0a41169bef810d2a983a6` is dated 2019-08-27. README declares GPLv3 and v9.00.0347/April 2019 compatibility. Kisover's page recommends the in-game version and says its author also maintains Z-S. | Do not represent this GitLab snapshot as the current in-game pack. Record the exact selected version and confirm terms for current modifications before using them. |

Iridium is the recommended first base, with Signal Cartel the exploration follow-up if permission is established. A candidate's overview source and its layout author are separate provenance. User-provided full layouts can enter alongside these derivatives once their own source/permission facts are established. Do not require four source families before shipping a small useful collection.

Author confirmation on 2026-09-08: the user arranged both captured window layouts at **3840×2160 with 150% EVE UI scale** and chose **FlyGD Wingman** for the layout credit. This credit does not replace the overview-pack authors or their licence notices. The user identified the Z-S edition as **v10.07.29**; that attribution is author-reported pending verification of its upstream source/licence evidence, not an assertion that it equals the old v9 GitLab snapshot.

Earlier unsupplied candidates (including Iterami) are not launch commitments. No upstream code, installer scripts, personal captures or native YAML has been copied into the feature worktree. A native-parser refusal does not justify weakening it, and a recent repository activity date does not establish gameplay currency. Check the actual full exported artifact and its provenance before admission.

### Admission and maintenance

An artifact enters the release bundle only after:

1. Redistribution permission and attribution are established, including upstream conditions and the layout contributor's permission.
2. Existing full-artifact parsing succeeds after the explicitly proposed twenty-tab compatibility prerequisite, without other unreviewed adapter/schema expansion or lossy normalization. Retain eight groups and the supported unstacked-window subset. Do not trim incoming tabs to satisfy the obsolete eight-tab budget. A distinct representation refusal still needs a focused evidence-backed decision; increasing the tab budget is not permission to reinterpret unrelated fields.
3. A reviewer inspects text for unwanted personal content, verifies the claimed scope, and binds the review record to the exact hash.
4. Automated library-to-review-to-create tests exercise the unchanged importer with distinct recipient fixtures and the native codec.
5. The author/operator records an actual complete import into a disposable, independently initialized recipient and checks the named layout, groups and labels. Previous phase validation establishes the importer, not these new content choices. This is a usable feature check, not another sequence of isolated schema experiments.

Record content evidence in `docs/reference/curated-preset-content.md` and shipped concise metadata. Include relevant license text with bundled assets. Reviewers do not fabricate author/operator evidence. Feedback changes the content revision in a later release. Removed entries disappear from the catalog but do not remove imported profiles.

At least two genuinely useful, approved complete setups are required for initial feature acceptance. They may share an overview base but must offer distinct usable arrangements. If content is unavailable, report the feature as awaiting that dependency rather than reducing the acceptance floor. An empty, single-entry or synthetic-only catalog is not completion. Synthetic data stays in test fixtures and `dev.js` only. Community contributions follow the same admission process; distribution/publication permissions remain explicit.

## Compatibility prerequisite from the actual candidates

The user explicitly requested expanding the portable exporter rather than trimming real overview packs. Both designated Test-profile candidates were preserved outside the repository as private account/character/display snapshots, with all copied bytes hash-verified and source files/settings unchanged. Both now export/reparse and pass Windows native-codec new-profile/re-export checks against invented recipients; the checkpoint separates that engineering result from pending live-EVE and content admission. At acquisition, neither produced a valid full portable artifact; the original blockers were:

- Iridium-based default: nine saved tabs in three groups (6/2/1); export refuses the eight-tab budget.
- Z-S-based default: six saved tabs in three groups (4/1/1); eight saved filter definitions omit `alwaysShownStates`, and the existing adapter requires that field. Tab expansion alone does not solve this refusal.

**Approved bounded amendment (2026-09-08):** derive `setup_model.MAX_TABS` from the existing `setup_compat.CLIENT_TAB_SLOTS = 20`. The documented client slot domain and physical adapter already support IDs 0–19. Keep eight groups, 32 layout records, all reference/order/presence/geometry/stack checks and the existing file/node/depth budgets. One-group native input consequently accepts up to twenty tabs too; no separate per-window eight-tab validator exists. Test nine/twenty accepted, twenty-one refused, sparse-to-dense mapping through slot 19 and actual native-codec application/re-export. UI help already derives the backend limit.

Keep artifact version 1: field meanings and representation are unchanged. Older builds continue rejecting artifacts with more than eight tabs; document that receiving them requires an updated Wingman. This is an admission-budget expansion, not a restart of the earlier schema work.

The Z-S omitted-field case is a separate compatibility correction. Static inspection of the current public client establishes that `GetAlwaysShownStates` and `GetAlwaysShownStatesByPresetKey` use a dictionary lookup with an empty-list default; the constant names the exact `alwaysShownStates` field. Normalize only that omitted DAT field to a fresh empty list in the exported semantic definition. Keep other required fields, unknown-field/alias checks, present-invalid-value refusal and the strict portable JSON requirement unchanged. The same physical-definition reader covers affected recipient comparisons and canonical protected checks, which need regression coverage. Do not edit private captures or treat export/reparse success as content approval. The independently stated public-client evidence and hashes must accompany the correction; do not vendor client code.

Replaying Iridium after lifting the tab guard also reached legacy integer label styles: italic/underline integer zero, and Z-S contains underline integer one. The current client's raw label-field reads and truth-test formatting helpers establish their boolean effects. At the DAT projection boundary only, normalize exact integer zero to false for bold/italic/underline and exact integer one to true for underline. Preserve existing accepted bold/italic integer one, booleans, optional-field absence and ordered/repeated records. Other values remain refused; portable JSON validation is unchanged. This correction needs source/recipient/nonmutation and native-codec tests alongside the omitted-state correction, not additional schema experiments.

## Smallest complete UX

### Shape brief

Audience: an EVE multiboxer preparing clients before a session, using Wingman's dark utility window beside the game, not browsing a marketplace. The primary action is to choose a known complete setup and understand what the subsequent new-profile creation will change.

Use the existing restrained theme, typography and control vocabulary. Anchors are Wingman's own setup import source controls, setup review summary and formation review's explicit separation of candidates from committed state. No new title-bar destination, modal, thumbnail gallery, tags, search or card grid. Image direction probes are skipped: the harness has no native image generation; the important proof is rendered interaction within the existing app at its floor.

Add **Browse bundled setups…** beside Paste and Choose file in Import setup. It opens an inline region with a labelled native select, plain-text details and **Use preset** / **Close** buttons. No entry is selected or used automatically. Details include purpose, origin/attribution, content revision, intended display context and honest validation notes. All imported text is rendered through text properties, never HTML.

Opening, selecting, browsing details or closing changes neither the existing import input nor its review authority. **Use preset** reads and validates the selected artifact. If nonempty input would be replaced, use a page-owned confirmation naming the replacement. Do not clear the old input/review merely because a read started; a failed read or cancelled confirmation leaves both intact.

On a successful, still-current response, the setup owner replaces its input through the existing `importChanged(true)` path. This clears stale review authority and the native label-retention choice, but retains the chosen recipient/base and draft profile name. The user still chooses **Review**, then **Create profile**. Do not auto-review, infer a recipient account, create a profile or activate it in the launcher.

Show selected-origin information next to the loaded input. Manual text changes or replacement by Paste/File clear that attribution so edited input is not falsely represented as the exact reviewed bundled artifact. Copying or importing creates no persistent installed-preset registry.

The display notice remains explicit: resolution and UI scale stay local; layout geometry is copied as saved and may need manual adjustment. Library selection does not promise automatic fitting. Back, Cancel and already-sent Create outcomes retain existing behavior.

### States and lifecycle

- Loading list/entry: local status, no unrelated controls blocked. Disable duplicate catalog requests; leave Close and the route out available.
- Empty: "No complete setups are bundled in this build. Paste a setup or choose a file." This is a tested fallback, not the intended release content.
- Bad/missing catalog: visible local failure with retry. Manual Paste/File remains usable; no boot-time exception.
- Bad/missing/incompatible selected artifact: explain refusal; input and review remain unchanged.
- Stale result: ignore it after route exit/re-entry, picker close/reopen, selection change (including A → B → A), source edits, recipient/name changes, or Create initiation. Capture both view generation and input version, plus catalog request identity. A late confirmation answer has the same ownership checks. Existing Paste/File reads and catalog reads share the owner's source-version authority: whichever replacement is accepted invalidates the other's pending reply. A superseded source cannot overwrite text or restore bundled attribution.
- Dirty source replacement: confirm only the input replacement, not a saved-profile mutation. Cancelling preserves text, selection, review and focus.
- Creating/published: no catalog action may change the draft. Existing detached receipts still settle through Profiles' sole owner.
- Keyboard: labelled select, standard focus rings, Tab/Space/Enter, Close returning focus to the opener, successful Use focusing the imported input, and explicit hidden/display rules. Do not hijack an existing Escape/Back handler.

## Architecture and distribution data

Keep one new read-only module, `wingman/evesettings/setup_catalog.py`, under the existing package. It knows this catalog contains only full `ui-setup` artifacts; it is not a generic preset registry. `ProfilesController` wraps its read results/errors; `Api` keeps thin facades. No worker, mutable catalog state, subscription, new completion event or dependency is needed. `uisetup.js` owns the small picker directly.

New data lives under `wingman/assets/setup-presets/`:

- `catalog.json` for distribution metadata.
- `<id>-r<revision>.json` for exact full preset artifacts (filename derived from validated ID/revision, not an arbitrary manifest path).
- License text files using validated plain basenames.

Proposed manifest v1: exactly `{format: "wingman-setup-catalog", version: 1, entries: [...]}`. Each entry has exactly `id`, `revision`, `title`, `description`, `sha256`, `overview_sources`, `layout_author`, `display`, and `verification`.

- `id`: ASCII lowercase slug `[a-z0-9]+(?:-[a-z0-9]+)*`, maximum 64 characters; unique across entries.
- `revision`: nonboolean integer 1–2,147,483,647. One current revision per ID. Any artifact-byte change requires a new revision and hash; editorial metadata corrections need not change artifact revision.
- `title`: 1–128 code points; `description`: 1–2,048.
- `sha256`: exactly 64 lowercase hex characters, of the exact UTF-8 artifact bytes. This detects mismatches, not authenticity if an attacker replaces both files.
- `overview_sources`: 1–8 exact records `{name, author, reference, version, license, license_file}`. `reference` is inert provenance text, never fetched/opened by this feature. Each text field is nonempty and at most 512 code points; `license_file` is a plain `[a-zA-Z0-9_-]+.txt` basename of at most 128 characters. License terms are a human admission gate, not inferred from passing schema checks.
- `layout_author`: 1–128 code points, with contributor permission.
- `display`: exactly `{width,height,ui_scale_percent}`. Nonboolean positive integers; width/height at most 32,768; scale 1–1,000. These are metadata bounds, not new supported-EVE-scale claims. No unknown/inferred values: the author supplies them.
- `verification`: 1–2,048 code points describing only recorded checks, with an evidence reference to the content record. No automatic "verified" badge based on parser success.
- All text must be valid UTF-8 and free of control characters. Reject unknown fields and duplicate JSON object keys.

Manifest budget: 128 KiB UTF-8 before decode, at most 64 entries. Catch decoding/recursion errors; validate the shallow structure before projection. Do not eagerly load every artifact when browsing. Read the selected regular file, refusing symlink/reparse aliases, with the existing setup text byte ceiling (2 MiB), check hash, then run `parse_text` and require a full Wingman setup, not merely accepted native input. Do not reject a read-only resource merely for having multiple hard links: package installers may legitimately use them, and the artifact's exact hash still binds its contents. Summary comes from `summarize`, not catalog claims. Source/frozen asset-directory and license-file containment are tested; no caller-supplied path or URL reaches file I/O.

Proposed pure/read-only interfaces:

- `setup_catalog.list_entries() -> list[dict]`: bounded validated metadata only.
- `setup_catalog.read_entry(preset_id: str, revision: int, sha256: str) -> dict`: returns `{entry, text, summary}` only for an exact current catalog match. Re-read the manifest rather than trusting UI metadata; reject changed identity/revision/hash.
- `SetupCatalogError(ValueError)`: recoverable, actionable catalog failures.
- `ProfilesController.setup_catalog() -> dict`: `{ok, entries, error}`.
- `ProfilesController.setup_catalog_entry(preset_id, revision, sha256) -> dict`: `{ok, entry, text, summary, error}` on success/refusal as appropriate.
- API facades: `eve_settings_setup_catalog()` and `eve_settings_setup_catalog_entry(preset_id, revision, sha256)`.

These endpoints perform no settings writes, review creation or EVE process checks. The unchanged later `setup_review` / `setup_create` enforce actual recipient applicability. Catalog validity does not imply every recipient is supported.

Add `paths.setup_presets_dir()` with source/package and frozen asset resolution matching explicit packaging locations. No PATH fallback, writable cache or installed-directory mutation. Declare package data for normal distributions and explicitly collect these assets into PyInstaller's `assets/setup-presets`. A post-freeze inventory/hash assertion validates actual referenced files, not just directory existence. No application version bump or release dispatch is part of implementation approval.

## Verification and execution agreement

Use named `smart` implementers and independent `review` agents, without nested agents. After plan approval execute continuously with TDD, task reviews, scoped corrections, `polish-core --fix`, inspection of polish edits, independent whole-change review and fresh verification. No routine milestone permission prompts.

Full suite prerequisites: Node on PATH, locked dev environment, and built/installed release codec under this linked checkout's `packaging/bin`; follow `docs/overview-layout-sharing-verification.md#local-verification-prerequisites`. Run focused Python/production-JS harnesses, full pytest with skip inspection, Ruff lint/format, JS smoke, Cargo and diff checks. Missing Node/native coverage is not a pass.

Render the actual dev UI at 840x625 and 839x621 for loaded/empty/error/long metadata, replacement confirmation, keyboard/focus and delayed source replacement. Browser/DOM results do not establish Windows/WebView2, frozen runtime or EVE behavior. Windows and candidate-content acceptance remain accurately identified external checks requiring applicable authorization.

Preserve the old overview worktree and recovery evidence. Do not push, open a PR, publish community content, dispatch a build, install, change live profiles or drive EVE/launcher without applicable authorization. Content generation by the user does not grant blanket access to private evidence.

## Independent proposal review

A read-only independent `review` agent approved the architecture/scope direction and requested two corrections: require two useful complete setups rather than allowing a single-entry completion, and explicitly test races between existing Paste/File reads and catalog selection, including A → B → A selection. Both are incorporated above and in the implementation plan. This review produced no runtime, packaging, browser or EVE evidence. User approval of the complete proposal is still required.

## Exclusions and adaptation points

No formation changes; no native-overview-only library entries; no unapproved schema/adapter expansion beyond the documented tab-budget and physical-DAT compatibility prerequisites; no synthesized full layout from recipient data; no automatic fitting; no hosted catalog; no authentication; no community publishing UI; no installed-preset tracking or update reminders; no screenshots of private layouts committed; no unrelated refactors.

Revisit the plan only if an actual supplied artifact is refused by the shipped support boundary, redistribution rights are unavailable, its geometry requires unsupported stacks/windows, or proposed content cannot be validated. Do not silently broaden the schema or substitute an empty catalog. Routine copy/layout choices within this brief are local implementation decisions, not new approval gates.
