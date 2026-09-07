# Overview and In-space Layout Sharing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export a faithful Wingman overview/in-space-layout preset and apply it to a new recipient profile, preserving recipient-local display preferences and existing profiles.

**Execution checkpoint:** Tasks 1–3 are implemented and task-reviewed at `904d1a8`; Task 4 is blocked on protected/default, selection/cache and surplus-window retirement evidence. See [verification and decisions](overview-layout-sharing-verification.md). This is not a completed feature or release sign-off.

**Architecture:** Pure validation and decoded-document adapters feed a recipient-local staged profile constructor. `ProfilesController` owns context, review authorization and mutation lifecycle; `Api` remains a thin facade with named file-dialog ports. One focused Profiles subroute owns transient UI state and receives completion through the existing event owner.

**Tech Stack:** Python 3.11+, existing settings codec, pywebview 6.2.1, plain HTML/CSS/ES5, Node runtime tests, PyYAML added for bounded native-YAML compatibility, pytest/Ruff, Windows and Linux CI.

**Spec:** [overview-layout-sharing-design.md](overview-layout-sharing-design.md). Read it and [the discovery record](overview-layout-sharing-discovery.md) before implementation. This plan is based on repository `a38c7a0`, with the reviewed design committed in `92e7d9a`.

## Global Constraints

- Copy saved layout geometry as-is. Do not implement automatic fitting.
- Preserve recipient-local resolution, display mode, monitor preferences and UI scaling. Never move or resize a running EVE client.
- New profile only; never overwrite an existing profile through this feature.
- One source character/account pair; one recipient character/account pair. Both local files and their confirmed association are required.
- EVE must be positively confirmed CLOSED for export snapshots, review snapshots and profile publication. RUNNING and UNKNOWN refuse.
- No raw DAT document, codec envelope, source path, account/character ID, checksum, content revision, local timestamps, history or hardware preference file in the artifact.
- User-authored names and label markup are text, not anonymized; render them as text in Wingman.
- Preserve ordered ship-label multiplicity. Do not turn labels into a type-keyed dictionary.
- Supported windows must be unstacked. Refuse affected sender/recipient stacks, including surplus overview instances being retired.
- Native YAML is configuration-only. Ambiguous labels require explicit **Keep my ship labels**; supplied YAML tabs become one primary overview group, without importing geometry.
- Both inputs: 2 MiB UTF-8 byte ceiling; maximum nesting depth 16; total 100,000 parsed-node budget.
- Version 1: at most 256 filter definitions, eight tabs, eight nonempty overview groups, 64 label records and 32 layout records.
- Group/state IDs: nonnegative signed-32-bit integers, never booleans; membership lists at most 8,192 IDs. Names at most 512 Unicode code points; individual label text fields at most 4,096.
- Geometry: first two coordinates within -32,768 to 32,768; four size/reference-size values positive and at most 32,768. Target-origin pair finite and within 0–1; supported integer HUD offset within -32,768 to 32,768. Never clamp.
- Preserve recipient `core_public__.yaml` and `prefs.ini` bytes locally; refuse a base missing either file. Never obtain them from the artifact.
- Do not broaden `tree.file_kind()` or ordinary profile-copy/backup/restore semantics. Do not create a generic preset registry or another runtime controller.
- No new title-bar destination. Preserve the 840x625 logical-pixel floor, handler ownership, wrapped controls, text rendering and route cleanup.
- All repository writes occur in a linked worktree. Private evidence stays outside Git. Tests use synthetic data and Linux `/tmp` where appropriate, never real user profiles or clipboard.
- Each task ends with focused verification and a reviewable commit. Run polish with safe fixes after implementation, inspect edits, then rerun verification. Do not merge or release without authorization.

---

## Evidence, decisions and review risk

1. **A fresh recipient must demonstrate the imported result.** Native YAML reproduced 42 custom definitions/eight tabs but no three-window grouping or placement; nine labels became six. The earlier sender clone is not a blank-recipient test. Task 11 keeps a genuinely fresh baseline and distinguishes startup behavior from import.
2. **Temporary context browsing cannot persist selection.** `controller.state` describes only the selected profile (`controller.py:427–590`); `select` persists selection (`:760–819`). Add a read-only `setup_context` instead of calling `eve_settings_select` while browsing the import base. Cancel then changes neither files nor Wingman settings.
3. **New-profile construction is richer than ordinary profile copy.** `profilecopy.stage_copy` clones only `tree.file_kind` members; that excludes local YAML/INI. Compose its staging mechanism with a narrow local-preference copy and a complete byte-revision manifest, not a global classifier change.
4. **Creation is the commit action.** Before Create is sent, Cancel discards review and changes nothing. Once it is sent, the UI cannot promise cancellation: acceptance/publication may precede the starter reply. An accepted worker either publishes one complete profile or refuses. During that interval the exit is **Back**, not Cancel; leaving does not authorize undo or silently stop accepted work.
5. **Current ownership must survive.** `ProfilesController`/`ProfilesPorts` own the topology (`controller.py:36–58,139–205`); `Api._build_profiles_controller` supplies effects (`ui/api.py:6216–6237`). Do not transplant pre-extraction code into the facade.
6. **Publication and remembering selection are separate.** Reuse the outcome distinction demonstrated by `_eve_select_created_profile` and `_eve_copy_profile_worker` (`controller.py:1715–1893`). A published profile remains success if subsequent selection/status housekeeping fails.
7. **Schema uncertainty is an explicit stop gate.** The field-map/default/cache proof in Task 1 must be resolved before enabling the writer. Do not substitute prefix guesses, blindly reset sections, or cite codec round-trip success as proof that EVE interprets a field correctly.
8. **The launcher caches a disk scan.** Its inspected startup scan recognises `settings_*` directories; copied DATs are not immediate launcher visibility. Explain a launcher restart after creation and verify it manually; do not edit launcher account/registration stores.

Rejected alternatives: wholesale sender cloning leaks unrelated state; YAML-as-full-preset loses layout/labels; in-place multi-file replacement requires stronger crash recovery; private launcher-state editing is unnecessary; automatic geometry fitting is explicitly deferred.

## File map and responsibility

Proposed files are new work, not missing existing modules.

| File | Responsibility |
| --- | --- |
| `wingman/evesettings/setup_model.py` | Supported constants, semantic model validation, limits and summary projection |
| `wingman/evesettings/setup_sharing.py` | Strict Wingman JSON envelope, canonical serialization, bounded input dispatch |
| `wingman/evesettings/overview_yaml.py` | Safe native-YAML parsing and explicit normalization/limitations |
| `wingman/evesettings/setup_documents.py` | Exact owned-field projection and application over decoded recipient documents |
| `wingman/evesettings/setup_profile.py` | Local file manifests, richer hidden staging and new-profile publication |
| `wingman/evesettings/controller.py` | Read-only context, one private review offer, identity checks, file operations and create worker |
| `wingman/ui/api.py` | Thin delegates; late-bound native input/output dialog ports |
| `wingman/web/uisetup.js` | Export/import UI state, review, clipboard truthfulness and completion correlation |
| `wingman/web/{app,evesettings,dev}.js`, `index.html`, `style.css` | Narrow route/opener/forwarding/dev/markup/style integration |
| `tests/setup_fixtures.py`, `tests/fixtures/ui_setup/` | Synthetic sender/recipient/model/native fixtures and deterministic test setup |
| `tests/test_ui_setup_{schema,model,sharing,yaml,documents,profile,controller,page,integration}.py` | Corresponding boundaries and integrated behavior |
| `tests/fixtures/ui_setup_page.cjs` | Actual page module/markup runtime harness; not a rendering certificate |
| `docs/ui-setup-field-map.md` | Proven field ownership, representations and cache/default rules |
| `docs/overview-layout-sharing-verification.md` | Actual test/manual results and unresolved release gates |

All production modules stay inside an existing package; no new setuptools subpackage is required. PyYAML still needs dependency, license and packaged-runtime verification.

## Shared contracts to implement

### Model and transport

`setup_model.SetupError` carries stable boundary error codes. `ParsedSetup` is an owned-per-call parsed value, not immutable merely because its outer dataclass is frozen:

```python
from dataclasses import dataclass
from typing import Literal

class SetupError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

@dataclass(frozen=True)
class ParsedSetup:
    source_kind: Literal["wingman", "native-yaml"]
    overview: dict
    layout: dict | None
    ambiguous_labels: bool = False
    warnings: tuple[str, ...] = ()
```

Never retain its mutable dictionaries as review authority or expose recipient documents to JavaScript. The controller offer retains the original input text, explicit choices and an immutable manifest; the worker reparses into its own model.

Wingman envelope fields are exactly `format`, `version`, `type`, `overview`, `layout`; values are `wingman-preset`, integer `1`, `ui-setup`, and the two components. Semantic fields use readable names, not `bytes:`/`utf8:` codec keys:

- `overview.presets`: ordered records with `name`, `groups`, `filteredStates`, `alwaysShownStates`.
- `overview.tabs`: ordered records with `id`, `name`, `overview`, `bracket`, `color`, `tabColumns`, `tabColumnOrder`.
- `overview.windowGroups`: ordered nonempty lists of tab IDs.
- `overview.shipLabels`: ordered records with the proven `type`, `pre`, `post`, `state` and optional supported formatting fields. Preserve null-type duplicates.
- `overview.settings`: the explicitly mapped appearance/state aggregates and scalar settings from Task 1. For full Wingman input, absent supported overrides normalize to clear/reset semantics. For native input, absence means retain, as specified.
- `layout.windows`: records with `key`, `geometry`, `state`. A full export covers all fixed allowlisted window slots (including absent/default overrides) plus active overview ordinals; it is not an arbitrary selection of cached records. State properties are `open`, `minimized`, `collapsed`, `compact`, `locked`, `overlay`, `lightBackground`, mapped to the seven proven storage maps. Missing state properties clear that included window's corresponding override. Geometry may be null for an ordinary window using EVE defaults; active overview windows require a six-integer record.
- `layout.targetOrigin`, `targetOriginLocked`, `hudOffset`: explicit values or null to clear the corresponding override. Geometry and scalar values are copied as saved, not transformed.

Native input may omit components/aggregates. A supplied native tab set must include its filter dependencies or an explicitly supported sentinel; do not bind a missing named dependency to an arbitrary same-named recipient preset. Filter-only native input preserves recipient tabs/grouping. Supplied native tabs produce one group and retire surplus recipient overview instances.

Define in Task 2:

- `setup_model.validate_wingman(value: object) -> ParsedSetup`
- `setup_model.validate_overview(value: object, *, partial: bool) -> dict`
- `setup_model.validate_layout(value: object, overview: dict) -> dict`
- `setup_model.summarize(value: ParsedSetup) -> dict`
- `setup_model.limits_payload() -> dict`
- `setup_model.check_text_budget(text: str) -> None`
- `setup_model.check_structure_budget(value: object) -> None`
- `setup_sharing.parse_text(text: str) -> ParsedSetup`
- `setup_sharing.export_text(value: dict) -> str`

Define in Task 3: `overview_yaml.parse_text(text: str) -> ParsedSetup`. Keep `setup_model` a leaf: both parsers use its resource helpers, and the model never imports transport/document/controller modules. `setup_sharing` dispatches to `overview_yaml`, not the reverse. Dispatch recognizes a valid Wingman envelope strictly; a malformed/unsupported claimed Wingman artifact never falls back to a permissive YAML path.

### Decoded-document adapters

Task 4 defines:

- `setup_documents.export_setup(account: codec.Document, character: codec.Document) -> tuple[dict, tuple[str, ...]]` — portable envelope plus explanatory warnings.
- `setup_documents.apply_setup(account: codec.Document, character: codec.Document, parsed: ParsedSetup, *, keep_ship_labels: bool, now: float) -> tuple[codec.Document, codec.Document]` — new documents, never in-place mutation.
- `setup_documents.protected_definition_names(account_doc: dict) -> frozenset[str]` — only the proven Task 1 rule; uncertainty refuses affected conflicts.

Source/export and recipient/application stack checks are part of these adapters. Validate aliases and timestamped records before accessing a value; rebuild only known types. Reuse `formations.filetime(now)` for internal timestamps, not a new epoch formula.

### Profile manifests and staging

Task 5 defines the following data without mutable nested dictionaries:

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class FileRevision:
    name: str
    size: int
    sha256: str

@dataclass(frozen=True)
class ProfileManifest:
    profile: Path
    files: tuple[FileRevision, ...]
```

Interfaces:

- `setup_profile.capture_manifest(plan: profilecopy.ProfileCopyPlan) -> ProfileManifest`
- `setup_profile.require_manifest(plan: profilecopy.ProfileCopyPlan, expected: ProfileManifest) -> None`
- `setup_profile.stage_setup(plan, expected: ProfileManifest, account_filename: str, character_filename: str, parsed: ParsedSetup, *, keep_ship_labels: bool, now: float) -> context manager yielding profilecopy.StagedProfileCopy`

The manifest is the exact recognized DAT set plus the two required local files. It detects additions/removals as well as byte changes. Reject nonregular files, aliases/reparse points and hierarchy escapes in the setup source; do not follow a special file merely because its name looks recognized.

### Controller and facade

Task 6 adds these controller methods and same-named facade methods with the `eve_settings_` prefix:

| Controller method | Parameters | Reply |
| --- | --- | --- |
| `setup_limits` | none | limits dict |
| `setup_context` | `profile: str` | `{ok, error, root, server, profile, profiles, accounts, characters, account_identity_available, setup_available}` |
| `setup_export` | `expected_profile: str, account_path: str, character_path: str` | `{ok, error, text, summary, warnings}` |
| `setup_read_file` | none | `{ok, cancelled, error, text}` |
| `setup_save_file` | `text: str` | `{ok, cancelled, error, path}` |
| `setup_review` | `text: str, expected_profile: str, account_path: str, character_path: str, destination_name: str, keep_ship_labels: bool = False` | `{ok, error, error_code, review_id, summary, warnings, needs_label_choice}` |
| `setup_discard` | `review_id: str` | bool, false for stale/busy/already-consumed offer |

Task 7 adds `setup_create(review_id: str, request_id: str) -> dict` returning `{accepted, error}`, and controller-private `_eve_setup_create_worker(offer: _SetupReview, request_id: str) -> None`. Add controller imports for `setup_model`, `setup_sharing`, `setup_documents` and `setup_profile`; retain its existing `evesettings_profilecopy` alias. All setup names in this table are **new interfaces**, not existing methods.

New named ports:

- `choose_setup_input: Callable[[], str]`
- `choose_setup_output: Callable[[str], str]` — suggested filename in, chosen filename or empty string out.

One controller-private `_setup_review` slot owns the current offer. Define this private value in `controller.py` after its existing context types:

```python
@dataclass(frozen=True)
class _SetupReview:
    review_id: str
    text: str
    keep_ship_labels: bool
    selection_context: _EveContext
    generation: int
    plan: evesettings_profilecopy.ProfileCopyPlan
    account_filename: str
    character_filename: str
    account_id: str
    character_id: str
    manifest: setup_profile.ProfileManifest
```

`selection_context` captures the original controller selection, while `plan.source` may be a different sibling base chosen through read-only browsing. Do not require those profile paths to equal each other. At acceptance/publication, verify the original selection is unchanged and independently revalidate the chosen base/pair. Do not retain a live nested settings section or page-owned dictionary.

Creation completion uses existing `onEveSettingsDone` with:

```python
{
    "ok": True,
    "operation": "ui_setup_create",
    "request_id": request_id,
    "review_id": review_id,
    "published": True,
    "path": str(created),
    "selection_persisted": selection_persisted,
    "error_code": "",
    "error": "",
    "warning": warning,
}
```

Failure emits the same fields with empty path unless publication occurred. Error codes distinguish `invalid_request`, `stale_review`, `eve_not_closed`, `unsupported_setup`, `missing_local_preferences`, `destination_exists` and `create_failed`. Once `published` is true, later housekeeping cannot change it to failure.

### Page interface

New route: `uisetup`, markup `route-uisetup`, module `uisetup.js`.

- `WM.openUiSetup({mode: 'export'|'import', context: payload, preferred_character: path})` copies only needed context fields, initializes a new view generation and routes to the tool.
- `WM.uiSetupDone(payload)` accepts only matching operation/request/review IDs and the active view generation.
- Existing `evesettings.js` remains the sole `onEveSettingsDone` owner and forwards to this function.
- Add `uisetup` to route mapping, Profiles highlighting, `CHROMELESS_ROUTES`, and `EVE_ROUTES`, not to peer `last_destination` choices.
- Add Share/Import controls to existing Profile tools. `#es-source` may prefill a character; copy-target checkboxes never become setup recipient mapping.

---

## Task 1: Establish the owned-field map and synthetic fidelity fixtures

**Files:** Create `docs/ui-setup-field-map.md`, `tests/setup_fixtures.py`, `tests/fixtures/ui_setup/{source-account,source-character,recipient-account,recipient-character,wingman-preset}.json`, `tests/test_ui_setup_schema.py`.

**Consumes:** approved spec and authorized retained evidence; existing codec JSON representations and `formations.filetime`.
**Produces:** the proved field/default/cache table and fixture helpers below, with no production writer exposed.

- [ ] Inspect retained authorized sender/native-result evidence, not a newly scanned set of private files. Record section/key aliases, stamped-value shape, owned subkeys, missing-value semantics, cross-references and source/recipient reset behavior. Include presets/unsaved overrides, tab groups, labels, state colours/blinks, seven window-state maps, target origin and HUD offset.
- [ ] Establish protected-definition classification and the exact selection/cache references affected by replacement. A `DefaultPreset_*` prefix and successful codec round-trip alone are not a complete proof. If a required rule remains unproven, stop before Task 4 enables it and request a narrow authorized observation; do not invent or widen a reset.
- [ ] Build fixtures **from scratch** using invented names/IDs. Include three overview groups/eight tabs, nine ordered labels with four null types, both observed label-field variants, an unsaved override, stale `overview_3` geometry, distinct recipient data and synthetic unrelated/private sentinels. Do not scrub a full private document and call the result safe.
- [ ] Define helpers `wire() -> dict`, `documents(case='source') -> tuple[codec.Document, codec.Document]`, `install_lossless_codec(monkeypatch) -> None`, and `seed_profile(tmp_path, *, case='recipient', name='Base') -> ProfileFixture`. `ProfileFixture` has `root`, `server`, `profile`, `account_path`, `character_path`; use synthetic recipient IDs 20/30 and the recognized Tranquility server name. Seed through `codec.write_document` into test-only files; include distinct local YAML/INI bytes.
- [ ] Add fixture tests before factories. Representative fidelity assertion:

```python
from tests.setup_fixtures import wire

def test_fixture_has_the_label_multiplicity_native_yaml_lost():
    labels = wire()["overview"]["shipLabels"]
    assert len(labels) == 9
    assert sum(row["type"] is None for row in labels) == 4
    assert len(wire()["overview"]["tabs"]) == 8
```

- [ ] Implement the lossless transport fixture without replacing snapshot, verification or publication:

```python
from wingman.evesettings import codec

def install_lossless_codec(monkeypatch):
    def transport(mode, payload, **kwargs):
        if mode == "encode":
            return b"\x7d" + payload
        assert mode == "decode" and payload.startswith(b"\x7d")
        return payload[1:]
    monkeypatch.setattr(codec, "_run", transport)
    monkeypatch.setattr(codec, "codec_available", lambda: True)
```

- [ ] Run `uv run --no-sync python -m pytest tests/test_ui_setup_schema.py -v`; observe RED before helper implementation and GREEN after. Check that fixture IDs/text are synthetic and that the field map separates proven rules from unsupported cases.
- [ ] Commit: `git add docs/ui-setup-field-map.md tests/setup_fixtures.py tests/fixtures/ui_setup tests/test_ui_setup_schema.py && git commit -m "test: define setup schema fidelity fixtures"`.

**Gate:** no user-visible export/apply until owned fields and dependencies are proven. Unsupported non-null formatting variants must refuse, not be guessed from the nine-entry sample.

## Task 2: Implement the semantic model and strict Wingman JSON transport

**Files:** Create `wingman/evesettings/setup_model.py`, `wingman/evesettings/setup_sharing.py`, `tests/test_ui_setup_model.py`, `tests/test_ui_setup_sharing.py`.
**Consumes:** Task 1 fixtures/map. **Produces:** the model/JSON interfaces above; native dispatch remains a clear unsupported-input refusal until Task 3.

- [ ] Write the round-trip and validation tests first:

```python
from tests.setup_fixtures import wire
from wingman.evesettings import setup_sharing

def test_json_roundtrip_preserves_order_and_geometry():
    original = wire()
    parsed = setup_sharing.parse_text(setup_sharing.export_text(original))
    assert parsed.overview["shipLabels"] == original["overview"]["shipLabels"]
    assert parsed.overview["windowGroups"] == original["overview"]["windowGroups"]
    assert parsed.layout == original["layout"]
```

- [ ] Cover wrong marker/version/type; duplicate JSON fields and logical IDs; text/surrogates/NUL; bool-as-int/nonfinite numbers; every spec bound at/beyond boundary; geometry records; exact-case names; dangling/duplicate tab assignments; label type multiplicity versus invalid duplicate preset names. Keep parameter IDs short (`id='byte-limit'`, not the large payload).
- [ ] Implement the declared `ParsedSetup`, one allowlist/limit source, explicit primitive validators and new-copy normalization. Reject duplicate keys rather than overwriting them:

```python

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate field: {key}")
        result[key] = value
    return result
```

Use that hook in the byte-bounded JSON decoder; reject nonstandard constants, catch recursion failures, then count structure depth/nodes before domain conversion. Canonical output must also fit the byte budget. Do not normalize case, sort ordered labels/tabs or clamp coordinates.
- [ ] Define the exact supported settings/formatting variant tables from Task 1 in this task, and assert fixture compatibility. `summarize` returns counts/window labels/limitations only, not a decoded document. `limits_payload` derives all user-visible budgets from constants.
- [ ] Run both new test files RED/GREEN, then `tests/test_evesettings_formation_sharing.py` to prove the old format is unchanged. Run Ruff and formatting on new Python files.
- [ ] Commit: `git add wingman/evesettings/setup_model.py wingman/evesettings/setup_sharing.py tests/test_ui_setup_model.py tests/test_ui_setup_sharing.py && git commit -m "feat: validate portable setup JSON"`.

## Task 3: Normalize bounded native YAML with explicit compatibility choices

**Files:** Create `wingman/evesettings/overview_yaml.py`, `tests/test_ui_setup_yaml.py`, `tests/fixtures/ui_setup/native-complete.yaml`; modify `wingman/evesettings/setup_sharing.py`, `pyproject.toml`, `uv.lock`, `THIRD-PARTY-NOTICES.md`.
**Consumes:** model validators. **Produces:** `overview_yaml.parse_text` and native dispatch to `ParsedSetup(source_kind='native-yaml', layout=None)`.

- [ ] Write tests for 42 synthetic definitions/eight tabs/nine labels, filter-only input, absent aggregates, exact sentinel/reference handling and an ambiguous-label flag without losing records:

```python
from pathlib import Path
from wingman.evesettings import setup_sharing

def test_native_input_does_not_fabricate_layout_or_drop_labels():
    text = Path("tests/fixtures/ui_setup/native-complete.yaml").read_text(encoding="utf-8")
    parsed = setup_sharing.parse_text(text)
    assert parsed.source_kind == "native-yaml"
    assert parsed.layout is None
    assert parsed.ambiguous_labels
    assert len(parsed.overview["shipLabels"]) == 9
```

- [ ] Add malicious tags/anchors/aliases/cycles, duplicate mapping and pair-list keys, unsupported colour names, nesting/node/byte boundaries and malformed Wingman-envelope fallback tests. Pair lists need duplicate checks where their first entries are keys. Label records are an ordered collection instead: repeated types, including null, are not duplicate mapping keys.
- [ ] Run `uv add PyYAML`, inspect that dependency/lock changes are limited to the required dependency, and verify the installed package license before adding its notice. Use SafeLoader plus a bounded event preflight; never enable Python constructors.
- [ ] Map only observed native fields. Convert colour-name entries using a verified EVE palette table, not CSS colours; convert `background_<id>`/`flag_<id>` keys into explicit records. Preserve ordered arrays. Reject an unverified name/variant with a clear compatibility error.
- [ ] For supplied tabs construct one group; for absent tabs retain absence in the partial model. Mark ambiguous labels for explicit retention at review. Native input never becomes a full Wingman artifact by borrowing recipient geometry.
- [ ] Run the YAML and JSON/model tests RED/GREEN; run locked sync and package notice checks. Do not weaken resource budgets to admit an exploding fixture.
- [ ] Commit: `git add wingman/evesettings/overview_yaml.py wingman/evesettings/setup_sharing.py tests/test_ui_setup_yaml.py tests/fixtures/ui_setup/native-complete.yaml pyproject.toml uv.lock THIRD-PARTY-NOTICES.md && git commit -m "feat: parse limited native overview YAML"`.

## Task 4: Project and apply only the proved decoded-document fields

**Files:** Create `wingman/evesettings/setup_documents.py`, `tests/test_ui_setup_documents.py`; update the field map only with newly verified evidence.
**Consumes:** validated model, Task 1 field map. **Produces:** `export_setup`, `apply_setup`, `protected_definition_names`.

- [ ] Write source immutability, recipient preservation and full-fidelity tests first:

```python
import copy
from tests.setup_fixtures import documents
from wingman.evesettings import setup_documents, setup_sharing

def test_apply_uses_recipient_documents_and_preserves_all_labels():
    source = documents("source")
    recipient = documents("recipient")
    original = copy.deepcopy(recipient)
    wire, warnings = setup_documents.export_setup(*source)
    parsed = setup_sharing.parse_text(setup_sharing.export_text(wire))
    account, character = setup_documents.apply_setup(
        *recipient, parsed, keep_ship_labels=False, now=1000.0
    )
    assert recipient == original
    roundtrip, _ = setup_documents.export_setup(account, character)
    assert roundtrip["overview"]["shipLabels"] == wire["overview"]["shipLabels"]
    assert roundtrip["layout"] == wire["layout"]
```

- [ ] Implement strict owned-key helpers privately in this module: refuse multiple typed aliases for the same semantic key, malformed stamped tuples and unsupported owned value shapes. Preserve the chosen recipient key representation; encode only known field/value types. Never call the codec on payload-supplied raw documents.
- [ ] Export effective supported definitions (valid unsaved overrides take precedence), reference closure, labels, groups and supported layout. Return an unsaved-override count warning; export neither cache nor revision/history/identity metadata.
- [ ] Apply to deep copies of recipient documents. Replace active tabs/settings/groups coherently; upsert incoming custom definitions; retain unrelated definitions and recipient default identity. Apply the proven protected-definition/cache rule. Clear imported-name unsaved overrides and reset only known invalidated references to a valid imported selection.
- [ ] Apply layout state/geometry as-is, including null/absent override semantics. Detect stacks in all affected windows, including retired overview instances; refuse before any filesystem operation. Never copy stack IDs or stale cached overview instances as active windows.
- [ ] Test YAML with explicit keep-label choice: exact recipient label sequence retained, supplied tabs become one group, primary/non-overview geometry retained, surplus overview instances retired, absent scalar/aggregate settings retained. Test missing choice refusal and filter-only input keeping current grouping.
- [ ] Add privacy sentinels, bytes/UTF8 alias collisions, protected identical/conflicting definitions, missing geometry, every observed label variant, unsupported stacks and all six unchanged geometry values. Round-trip modified documents with the real codec when available, without treating that as EVE acceptance.
- [ ] Run `tests/test_ui_setup_documents.py` RED/GREEN plus model/transport tests, then commit `feat: project and apply supported setup fields` with only this task's files.

## Task 5: Build complete recipient profiles in hidden staging

**Files:** Create `wingman/evesettings/setup_profile.py`, `tests/test_ui_setup_profile.py`.
**Consumes:** document adapters and existing `profilecopy` APIs. **Produces:** manifest/staging interfaces defined above.

- [ ] Write tests proving recognized-file/local-preference membership, exact hashes, both selected documents, unrelated files, source immutability and no destination before publication:

```python
from tests.setup_fixtures import install_lossless_codec, seed_profile, wire
from wingman.evesettings import profilecopy, setup_profile, setup_sharing, tree

def test_hidden_setup_stage_preserves_local_preferences(tmp_path, monkeypatch):
    install_lossless_codec(monkeypatch)
    base = seed_profile(tmp_path)
    found = tree.discover(base.root, base.server, base.profile)
    plan = profilecopy.prepare_copy(found, base.profile, "new", "Imported")
    manifest = setup_profile.capture_manifest(plan)
    parsed = setup_sharing.parse_text(setup_sharing.export_text(wire()))
    with setup_profile.stage_setup(
        plan, manifest, base.account_path.name, base.character_path.name,
        parsed, keep_ship_labels=False, now=1000.0,
    ) as staged:
        assert not plan.destination.exists()
        for name in ("core_public__.yaml", "prefs.ini"):
            assert (staged.path / name).read_bytes() == (base.profile / name).read_bytes()
        setup_profile.require_manifest(plan, manifest)
        created = profilecopy.publish_new(staged)
    assert created == plan.destination
```

- [ ] Enumerate only recognized DATs plus required local filenames, reject aliases/special files/escapes, hash exact bytes and re-enumerate at verification. A size/mtime match alone is insufficient. Report missing preference filenames directly.
- [ ] Compose `profilecopy.stage_copy(plan)`; copy local preferences into that same hidden directory and compare all staged base bytes with the reviewed manifest before patching. Validate both modified documents before encoding either. Yield the original `StagedProfileCopy` so its publication bookkeeping remains intact; use the richer manifest, not its DAT-only `members` tuple, for complete-file checks.
- [ ] Write only selected **stage** files through the existing codec, with expected revisions from the manifest. The no-op backup is deliberate for hidden disposable staging, never a live-file exception:

```python
from wingman.evesettings import codec

codec.write_document(
    staged_account_path, updated_account,
    backup=lambda _path: None,
    expected_content_revision=account_revision,
)
codec.write_document(
    staged_character_path, updated_character,
    backup=lambda _path: None,
    expected_content_revision=character_revision,
)
```

`staged_account_path`, `staged_character_path`, `updated_account`, `updated_character`, `account_revision` and `character_revision` are local values derived from the validated names, `apply_setup` result and manifest. Check local preferences remain byte-identical after patching. Yield for final controller rechecks; do not publish inside `stage_setup`.
- [ ] Inject failures copying each local file, encoding either document, codec verification, source additions/removals/replacements, symlinks/junctions, same-size edits and destination races. Assert no existing profile bytes change, no partial discoverable destination exists, and cleanup distinguishes pre- from post-publication failure.
- [ ] Run new profile tests RED/GREEN and existing `test_evesettings_profilecopy.py`, `test_evesettings_codec.py`, `test_evesettings_backup.py`. Confirm ordinary backup membership remains DAT-only.
- [ ] Commit `feat: stage recipient-local setup profiles` with this module/tests only.

## Task 6: Add read-only context, export/file operations and bound review

**Files:** Modify `wingman/evesettings/controller.py`, `wingman/ui/api.py`, `tests/test_profiles_controller_contract.py`, `tests/test_evesettings_controller.py`; create `tests/test_ui_setup_controller.py`.
**Consumes:** Tasks 2–5. **Produces:** read-only/file/review interfaces, two dialog ports and one private offer slot; no create action yet.

- [ ] Add RED tests for all new facade signatures/direct delegation, exact ports, construction-without-effects and runtime ownership. Extend existing contract tables/spies and the direct `ProfilesPorts` fixture in `test_evesettings_controller.py` in the same change; no intermediate missing-port failures.
- [ ] Extract only the existing file-description payload builder from `state` into a private method if needed for reuse; preserve existing state output exactly. `setup_context(profile)` validates a requested sibling in the currently selected root/server and returns its local roster without calling `select`, `_eve_persist_selection`, `resolve_names` or any settings-update port.
- [ ] Validate pairs from server-owned confirmed links intersected with real local files. Refuse off-Tranquility/unknown/deleted/ambiguous/missing/escaped pairs and discovery fallback. Add `setup_available` to state/context from codec availability; do not repurpose `formations_available` as a setup flag.
- [ ] Test the cancellation boundary explicitly:

```python
import copy
from dataclasses import replace
from tests.test_evesettings_controller import build_controller
from tests.setup_fixtures import install_lossless_codec, seed_profile

def test_context_browsing_does_not_persist_selection(tmp_path, monkeypatch):
    install_lossless_codec(monkeypatch)
    base = seed_profile(tmp_path)
    controller = build_controller(tmp_path)
    controller._settings["eve_settings"].update(
        root=str(base.root), server=str(base.server), profile=str(base.profile),
        account_characters={"20": ["30"]},
    )
    before = copy.deepcopy(controller._settings)
    writes = []
    controller._ports = replace(controller._ports, update_settings=writes.append)
    reply = controller.setup_context(str(base.profile))
    assert reply["ok"]
    assert controller._settings == before
    assert writes == []
```

The codec substitution is test-only; production still requires the bundled codec.
- [ ] Implement native dialog ports with late-bound `self._window`. Pinned pywebview returns a sequence or None and supports `save_filename`/`file_types`; add a lazy `_save_file_dialog_kind()` for `FileDialog.SAVE`. No generic callback port and no public non-method `Api` attribute.
- [ ] File input reads at most the byte ceiling plus one before UTF-8 decoding; strips a UTF-8 BOM but does not guess legacy encodings. File output validates Wingman JSON, uses a `.json` destination selected through the Save dialog and writes atomically. Cancellation returns `cancelled=True`; failures never report a saved path. Do not expose arbitrary path arguments on these endpoints.
- [ ] Export snapshots and review use the nonblocking Profiles hold and the strong `profile_copy_refusal` port. Export reads the selected pair with `codec.read_snapshot` and rechecks both exact revisions after projection; it does not need a dummy destination plan or require source preference files. Review captures the full chosen-base manifest before document reads and verifies it afterward, then dry-runs the same adapters used by creation. Bind its offer to input text/choice, exact pair, manifest and the original controller context/generation.
- [ ] Store only one offer. Clear the old offer at the start of an admitted new review, before parsing, so failed/replaced input leaves no old Create authorization. A successful review installs a fresh UUID. `setup_discard` clears only the matching unconsumed offer. Require explicit keep-label choice for ambiguous YAML and return `label_choice_required`/`needs_label_choice=True` without an offer.
- [ ] Run controller/contract tests RED/GREEN, including spy assertions that browsing/review/discard invoke no settings-write or publication effects, and read/write dialog tests. Commit `feat: review setup imports without persisting selections`.

## Task 7: Create profiles through one correlated controller worker

**Files:** Modify `wingman/evesettings/controller.py`, `wingman/ui/api.py`, `tests/test_ui_setup_controller.py`, `tests/test_profiles_controller_contract.py`.
**Consumes:** a private review offer and `stage_setup`. **Produces:** `setup_create` and the exact completion payload above.

- [ ] Write RED tests using existing `QueuedThreads` and `build_controller`: stale/unknown/replayed offer, invalid request ID, worker-start failure, busy/identification refusal, context/association changes, CLOSED→RUNNING/UNKNOWN changes, source changes and destination collision.
- [ ] Follow the nonblocking admission pattern of `copy_profile`, but **do not persist selection before publication**. Consume the matching offer only after validating it; restore it on a failed worker start only if it is still the same valid offer. Never queue creation behind another mutation.
- [ ] Worker reparses the immutable captured text, revalidates identity/context and manifest, constructs the hidden stage, then checks EVE, manifest and destination again immediately before `publish_new`. Release the lock in `finally` on every exit and emit exactly one completion.
- [ ] The critical sequence must remain structurally visible:

```python
from wingman.evesettings.setup_model import SetupError

refusal = self._ports.profile_copy_refusal()
if refusal:
    raise SetupError("eve_not_closed", refusal)
with setup_profile.stage_setup(
    offer.plan, offer.manifest, offer.account_filename, offer.character_filename,
    parsed, keep_ship_labels=offer.keep_ship_labels, now=time.time(),
) as staged:
    setup_profile.require_manifest(offer.plan, offer.manifest)
    refusal = self._ports.profile_copy_refusal()
    if refusal:
        raise SetupError("eve_not_closed", refusal)
    created = evesettings_profilecopy.publish_new(staged)
    published = True
```

The controller also performs the context/association checks described above; this sequence does not replace them. `offer` is the private reviewed value, never request-supplied paths or hashes. Preserve `SetupError.code`; map `codec.ContentChangedError` to `stale_review`, `FileExistsError` to `destination_exists`, and other codec/I/O failures to `create_failed` with useful context. Do not label an EVE-closed refusal as malformed input.
- [ ] Set publication success before selection/status effects. Reuse `_eve_select_created_profile`; a false result or thrown status effect adds a warning while keeping `ok=True`, `published=True` and the created path. Do not prune unrelated backups for a new-only operation.
- [ ] Test source/preferences unchanged, selected files changed only in the new profile, double Create producing one publication, old discard not cancelling accepted work, completion-before-start-reply and post-publish warnings. Prove the lock remains usable after every injected failure.
- [ ] Run controller, existing API profile/formations, facade and profile-copy suites, then commit `feat: create reviewed setup profiles atomically`.

## Task 8: Add the Profiles export tool and executable page harness

**Files:** Create `wingman/web/uisetup.js`, `tests/test_ui_setup_page.py`, `tests/fixtures/ui_setup_page.cjs`; modify `wingman/web/app.js`, `wingman/web/evesettings.js`, `wingman/web/dev.js`, `wingman/web/index.html`, `wingman/web/style.css`, `tests/test_profiles_page.py`, `tests/test_page_conventions.py`, `tests/test_dev_harness.py`.
**Consumes:** context/export/file APIs. **Produces:** route/opener/completion hooks and complete export flow; import control stays unavailable until Task 9 is complete.

- [ ] Add lexical route/gate/handler-ownership tests and a failing executable scenario before markup/module changes. Build the runtime harness from `PageTree` plus the actual production markup/module, following the formation harness without copying its scenario logic or introducing a generic framework.
- [ ] Harness invocation is `node tests/fixtures/ui_setup_page.cjs <markup-json> <scenario> <uisetup-js> <python-executable>`. Python serializes markup as UTF-8; all Node→Python JSON is explicitly decoded as UTF-8, independent of locale. Define deferred bridge/clipboard promises and mutation-call recording before scenarios.
- [ ] Implement `WM.openUiSetup`, the scoped route and Profile tools button. Use explicit character/account selection from local roster/confirmed links. Add the route to all four manual route/chrome/gate locations; do not add another peer destination.
- [ ] Use a view-generation guard for async work:

```javascript
var generation = 0;
function isCurrent(captured) {
  return captured === generation && WM.current_route === 'uisetup';
}
document.addEventListener('wm:route', function (event) {
  if (event.detail !== 'uisetup') generation += 1;
});
```

The real module also invalidates on opener/source/context changes and clears private draft/offer state. Event detail is the route name, not an invented `{to: ...}` object.
- [ ] Each export action snapshots the captured source pair. Show effective-unsaved warnings, included/excluded windows and the as-is/display notice. Copy reports success only after the real clipboard promise; Save reports success only after file-write reply. Ignore stale successes/errors and keep retry possible.
- [ ] Define runtime scenarios `export-source-change`, `export-route-exit`, `export-reopen`, `copy-denied`, `copy-unavailable`, `copy-late-success`, `save-cancel`, `save-failure`, `unsupported-stack`, `missing-pair`, `unicode-locale`. Assert no EVE mutation calls occur.
- [ ] Run the new runtime file plus lexical/bridge/dev checks RED/GREEN and Node syntax checks. Open the isolated dev page at 840x625; verify basic export layout without touching the real clipboard. Commit `feat: expose setup snapshot export in Profiles`.

## Task 9: Implement review, native limitations and explicit Create UI

**Files:** Modify `wingman/web/uisetup.js`, `wingman/web/evesettings.js`, `wingman/web/dev.js`, `wingman/web/index.html`, `wingman/web/style.css`, `tests/test_ui_setup_page.py`, `tests/test_dev_harness.py`, `tests/test_bridge_contract.py`, `tests/test_page_conventions.py` and `tests/fixtures/ui_setup_page.cjs`.
**Consumes:** all backend interfaces and Task 8 harness. **Produces:** complete import/review/create flow.

- [ ] Start with failing scenarios for temporary base browsing, cancelled review, pending text/name/base/character changes, ambiguous YAML labels and late completion. Add genuinely different per-profile rosters to `dev.js`; changing only a profile token with one flat roster is not a mapping test.
- [ ] Import owns text, base context, selected local pair, new name and keep-label choice separately from Profiles' persistent state. Read-only `setup_context` populates base choices. Any changed input clears the current review authorization and disables Create immediately. If a stale review reply arrives with a newly issued `review_id`, discard that exact ID; never let its cleanup clear a newer offer.
- [ ] Use namespaced DOM IDs such as `setup-text`, `setup-base`, `setup-character`, `setup-account`, `setup-name`, `setup-review`, `setup-keep-labels`, `setup-create`, `setup-status`, `setup-back`. The label choice is a wrapped checkbox with explicit wording, never a silent default.
- [ ] Review lists exact component/window counts, affected character/account, new profile, local-preference retention, unsupported/excluded scope and permanent display warning. YAML gets its configuration-only/single-group notice and an explicit label-retention choice where required; replacing the input text/file resets that choice. Render all names/markup with text properties.
- [ ] Register no new pushed handler. Extend the sole `evesettings.js` completion owner with a guarded `WM.uiSetupDone(payload)` forward, retaining existing formations handling. Match operation/request/review/view before modifying the tool. Set pending request identity before sending Create so immediate completion cannot be overwritten by a late starter reply.
- [ ] Before sending Create, install request identity, disable repeat Create/editing and switch the exit to Back; state that leaving does not cancel creation. A refused starter restores editing only if no matching completion already arrived, clears the authorization and requires fresh review. Before sending, Cancel discards review without creating a profile. On publication show the actual created name/path and launcher-restart instruction, preserving any selection/status warning.
- [ ] Required scenarios: `context-does-not-select`, `base-rosters-differ`, `review-invalidated-by-text`, `review-invalidated-by-name`, `review-invalidated-by-pair`, `old-review-after-new`, `cancel-during-review`, `yaml-label-choice`, `yaml-no-layout`, `stale-manifest`, `eve-unknown`, `double-create`, `start-refused`, `done-before-accepted`, `published-with-warning`, `route-exit-during-create`, `old-discard-after-new-review`, `labels-render-as-text`.
- [ ] Run runtime and lexical/bridge/dev suites and syntax checks. Browser-check ordinary/review/error states, maximum supported lists, long names, keyboard/focus, scroll and 840x625/839x621 floors in an owned isolated context. Record browser evidence as browser-only, not WebView2/EVE acceptance.
- [ ] Commit `feat: review and create imported setup profiles`.

## Task 10: Enforce integrated native/Windows test prerequisites

**Files:** Create `tests/test_ui_setup_integration.py`; modify `.github/workflows/ci.yml`, relevant packaging completeness tests and `docs/smoke-checklist.md`; create `docs/overview-layout-sharing-verification.md`.
**Consumes:** completed vertical flow. **Produces:** automated cross-boundary evidence and explicit remaining manual gates.

- [ ] Integration tests must call real facade/controller/document/manifest/staging code. Stub only external ports and, for the lossless variant, codec subprocess transport. Reuse source/recipient fixtures with deliberately different contents and confirmed synthetic pairs.
- [ ] Exercise both lossless transport and built native codec. Verify publication, exact recipient identities/unrelated data/local preferences, all nine labels, groups, geometry, effective overrides, stale manifests and representative copy/encode/publication failures. Include the YAML keep-label path with a deliberately different recipient label sequence.
- [ ] Make CI prerequisites fail visibly before pytest. Existing CI only runs `cargo test` after Python tests; it does not install the binary for availability-gated tests. Add `node --version`, a locked release codec build and the platform-correct binary copy before Test:

```bash
cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir packaging/settings-codec/target
```

The following is the body of a cross-platform Python step, invoked through `uv run --no-sync python`:

```python
import os
import pathlib
import shutil
from wingman.evesettings import codec

name = "wingman-settings-codec" + (".exe" if os.name == "nt" else "")
source = pathlib.Path("packaging/settings-codec/target/release") / name
target = pathlib.Path("packaging/bin") / name
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(source, target)
assert codec.codec_available(), "Native integration tests require the built codec"
```

Use an explicit compatible workflow shell for multiline script bodies on both runners; preserve existing action pins and failure annotations. Keep compiled outputs ignored, and keep the independent Cargo regression step.
- [ ] Verify PyYAML and any required extension are available in the packaged Windows app; update license/packaging assertions rather than relying solely on a development import.
- [ ] Run locked sync, full pytest with skip reasons, Ruff check/format, both Node harness syntax checks and Cargo tests. Inspect skips; native/Node coverage must not silently disappear in CI. No version bump or release is part of this task.
- [ ] Add smoke steps for fresh base initialization, display-file preservation, launcher restart/selection, supported windows/groups/labels, stacks refusing, YAML limitations, alternate recipient and error recovery. Verification record separates automated, browser, packaged-Windows and live-EVE evidence.
- [ ] Commit `test: exercise setup sharing across native boundaries`.

## Task 11: Polish, then prove the actual fresh-recipient workflow

**Files:** Only reviewed corrective source/tests if needed; update `docs/overview-layout-sharing-verification.md` and smoke results.
**Consumes:** Task 10's candidate. **Produces:** reviewer-facing completion evidence, or explicit blocked acceptance.

- [ ] Run `polish-core --fix` through its skill workflow, inspect every edit, add regression coverage for meaningful fixes and rerun focused/full verification. Follow with an independent named-range review of this branch; do not treat a design review as a code review.
- [ ] Record the exact candidate SHA/build before manual work. Use an authorized test installation/profile only. Do not repoint an existing launcher account silently, change real-client geometry or copy sender DATs into the fresh recipient.
- [ ] Have the operator create a genuinely fresh profile in the launcher, launch the intended recipient character, close EVE normally and capture the resulting baseline. Preserve that exact baseline separately before running Wingman's importer.
- [ ] Through the actual Wingman UI, export from the sender and create a new profile using the fresh recipient as its local base. Verify the base bytes remain unchanged and the new display preference files match the recipient base before launch.
- [ ] Restart/refresh the launcher, verify the new profile is offered, explicitly select it and launch the recipient. Check all supported windows/flags/grouping, all nine labels, filters/tabs/columns, target origin and HUD offset. Close normally and compare the saved result; document client normalization separately from data loss.
- [ ] Repeat with a deliberately different initialized recipient and a different display/scale. Preserve that recipient's display environment and verify truthful warning, not automatic fitting. Confirm unsupported affected stacks refuse without publication and the old profile remains available.
- [ ] Complete real clipboard, keyboard, screen-reader/focus, floor-size and applicable Windows scaling checks. If any environment is unavailable, leave its gate explicitly open and do not call the feature release-validated.
- [ ] Commit only actual corrections/results. Use `change-explainer` for the final write-up; offer branch integration/PR next, without merging or releasing automatically.

## Verification commands

Run the applicable row from the linked worktree after the task's RED/GREEN cycle;
new test counts are observed results, not numbers to invent in advance.

| Task | Focused command |
| --- | --- |
| 1 | `uv run --no-sync python -m pytest tests/test_ui_setup_schema.py -v` |
| 2 | `uv run --no-sync python -m pytest tests/test_ui_setup_model.py tests/test_ui_setup_sharing.py tests/test_evesettings_formation_sharing.py -q` |
| 3 | `uv run --no-sync python -m pytest tests/test_ui_setup_yaml.py tests/test_ui_setup_model.py tests/test_ui_setup_sharing.py -q` |
| 4 | `uv run --no-sync python -m pytest tests/test_ui_setup_documents.py tests/test_ui_setup_model.py tests/test_ui_setup_yaml.py -q` |
| 5 | `uv run --no-sync python -m pytest tests/test_ui_setup_profile.py tests/test_evesettings_profilecopy.py tests/test_evesettings_codec.py tests/test_evesettings_backup.py -q -rs` |
| 6 | `uv run --no-sync python -m pytest tests/test_ui_setup_controller.py tests/test_profiles_controller_contract.py tests/test_evesettings_controller.py -q` |
| 7 | `uv run --no-sync python -m pytest tests/test_ui_setup_controller.py tests/test_api_evesettings.py tests/test_profiles_controller_contract.py tests/test_evesettings_profilecopy.py -q -rs` |
| 8–9 | `uv run --no-sync python -m pytest tests/test_ui_setup_page.py tests/test_profiles_page.py tests/test_bridge_contract.py tests/test_page_conventions.py tests/test_dev_harness.py -q` |
| 10 | `uv run --no-sync python -m pytest tests/test_ui_setup_integration.py -q -rs` followed by all gates below |
| 11 | All gates below, plus actual recorded manual acceptance |

Full gates after integration and again after polish corrections:

```bash
uv sync --locked --extra dev
uv run --no-sync python -m pytest tests/ -q -rs
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
node --check wingman/web/uisetup.js
node --check wingman/web/evesettings.js
node --check wingman/web/app.js
node --check wingman/web/dev.js
node --check tests/fixtures/ui_setup_page.cjs
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
git diff --check
```

## Spec coverage and adaptation points

| Spec requirement | Tasks |
| --- | --- |
| Explicit schema, privacy, protected defaults/cache references | 1, 2, 4 |
| Ordered labels and effective filter overrides | 1–4, 10, 11 |
| Supported geometry/state/HUD; stack refusal; no fitting | 1, 2, 4, 8–11 |
| Native YAML budget, losses, explicit retention and grouping policy | 3, 4, 6, 9–11 |
| Confirmed local pairs; no persisted browsing; stale review protection | 5–7, 9, 10 |
| Recipient preferences, complete hidden staging, no existing-profile mutation | 5, 7, 10, 11 |
| Clipboard/files, route cleanup, truthful completion and launcher instruction | 6–11 |
| Fresh recipient, different recipient/display and real Windows acceptance | 10, 11 |

Stop and revisit the design if the proved field graph needs unapproved identity-dependent data or stack support; if protected/cache rules cannot be established; if EVE cannot retain the ordered label/geometry representation; or if native file variants need a broader safe-parser contract. Do not expand scope or weaken a refusal merely to make one artifact pass.

The following remain excluded: in-place setup replacement, whole-account-file sharing, automatic fitting, arbitrary stacks, personal chat/channel state, Neocom/info-panel configuration, ship-specific module arrangements, automatic launcher activation, fleet-wide role mapping, synchronization and a hosted library.

## Planning verification

Repository interfaces, controller locks/ports, facade tests, file-kind/staging rules,
pywebview 6.2.1 file-dialog signatures and CI ordering were inspected. A separate
read-only frontend inventory identified the nonpersisting-context requirement and
manual route/handler integration points. The plan's new files/interfaces are
proposals; no importer code or new test profile was created while planning.

The user approved subagent-driven execution. Tasks 1–3 and their actual results
are recorded in the [verification checkpoint](overview-layout-sharing-verification.md).
The remaining writer/GUI/acceptance tasks have not run; parser results do not
clear their persisted-data proof gates.
