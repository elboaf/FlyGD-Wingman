# Settings sharing: probe formations first

Date: 2026-09-06
Base: `57ce91d` — Harden accessibility, build reproducibility, and Settings docs (#171)
Status: agreed product scope; written design awaiting user review. No implementation authorized by this document.

## Outcome and roadmap

Players can exchange useful EVE settings between separate Wingman installations without exchanging account files or identities. The highest-value outcome is a complete ready-to-fly UI setup, not formations alone. Formations are the first release because their portable data model is already understood.

1. **Probe formations:** copy/paste selected named formations into an existing account's formation editor.
2. **Overview configuration:** share supported overview content without promising a complete window arrangement.
3. **Complete UI setups:** combine supported account and character components; default to a new EVE settings profile so the existing setup remains available.
4. **Curated library:** discover and distribute the same preset artifacts. Start with reviewed presets, not a community publishing service.

Individual presets target an existing profile with backups. Complete setups default to a new profile. Later phases require their own investigation and design; they are not included in the first implementation.

## Account versus character scope

Wingman's current mapping is in `wingman/evesettings/selective.py`:

| Account file (`core_user_<id>.dat`) | Character file (`core_char_<id>.dat`) |
| --- | --- |
| Overview profiles | Window layout |
| Probe formations | Neocom sidebar |
| Suppressed dialogs | Chat channels |
| Audio settings | Info-panel modes |
| Certain camera and graphics preferences | Docked panels |
| Market and contracts preferences | Search history and suggestions |
| Module slot layout / linked-weapons settings | |
| Window tab groups | |
| Search history and suggestions | |

These files are local to an EVE settings profile under a server/install directory (`wingman/evesettings/tree.py`). Account-level changes can affect other characters using the same account and profile; they are not promises of cross-machine synchronization. The mapping is not an exhaustive schema of every EVE setting. In particular, account-level storage does not make ship-specific entries portable.

A future complete UI preset will contain separate account and character components under one user-facing artifact. It must explain shared-account effects before applying. It must not imply that window geometry adapts across resolutions or UI scales until that behavior is implemented and verified.

## First-release user contract

### Copy

- Choose one or several formations from the current editor and copy them as one text artifact. Selection for sharing is separate from the formation currently displayed in the editor.
- Copy represents the current editor values, including valid unsaved edits. It does not save the account or reread older values from disk.
- Validate all selected formations before producing text. Invalid selected items fail the whole copy; invalid unselected drafts do not prevent copying valid items.
- Report success only after the clipboard write succeeds. Clipboard denial leaves the editor unchanged and reports the failure.

### Paste and review

- Open a page-owned paste surface with a multiline text field. Users paste normally; the application does not automatically read the system clipboard.
- Explicitly review the text. Validate the entire artifact before exposing candidates for addition. Malformed or unsupported input changes neither the draft nor the account file.
- Show candidate names, probe counts, editable names, and a preview using the existing formation projection. Review selection must not replace the current editor document.
- Names must be unique case-insensitively, both within the incoming batch and against the current draft. The user resolves target conflicts by renaming incoming formations or cancels. No automatic replacement, skipping, or renaming.
- An explicit **Add formations** action appends the whole reviewed batch to the current draft. Each new item has no local ID yet. Existing items and their IDs remain untouched.
- Mark the draft dirty and focus the first added formation. This is editor selection, not EVE's selected-formation setting.
- Cancel discards only the import review, including its proposed renames. It preserves existing unsaved edits.

### Save

- Only the existing explicit Save action writes the account file.
- Preserve the existing containment, mutation lock, EVE-closed check, backup, encode/decode verification, atomic publication, and post-save reload behavior.
- New IDs are minted by the existing formation writer. Adding formations must not redirect an existing valid EVE selected-formation pointer or modify scratch entries.
- Back/account-switch actions retain the editor's existing unsaved-change protection. Sharing adds no implicit save, reload, or route change.
- One destination account per editing session. No multi-account import in this release.

## Portable format

Use plain JSON text, with a format marker, integer version, and preset type. Only `probe-formations` is implemented initially. This identifies future artifacts without creating a generic settings registry or implementing future types now.

Example of a complete, minimal artifact (all distances are meters):

```json
{
  "format": "wingman-preset",
  "version": 1,
  "type": "probe-formations",
  "formations": [
    {
      "name": "Single probe",
      "probes": [
        {"x": 0, "y": 0, "z": 0, "range": 149597870700}
      ]
    }
  ]
}
```

The exporter constructs this shape explicitly; it never serializes a whole API response or decoded account subtree. Import accepts precisely this shape, with ordinary surrounding JSON whitespace. It rejects duplicate JSON object keys, unknown fields, unsupported format/type/version, and type coercions such as numeric strings or booleans used as numbers. It does not fetch URLs, execute anything, decode arbitrary marshal objects, decompress data, or extract text from Markdown fences.

The following transport limits are proposed design details for written review, not assertions about EVE's file-format limits:

- At most 64 KiB of UTF-8 text, checked before parsing.
- Between 1 and 32 formations per artifact; this is not a cap on the target account's existing list.
- Between 1 and 8 probes per formation, reusing the existing domain maximum.
- Names are trimmed, nonempty, at most 128 Unicode code points, and contain no control characters. Names remain user-authored text and may contain personal information; Wingman exports them as chosen, not as anonymized text.
- Coordinates and range are finite JSON numbers, not booleans; range is positive. Bound each coordinate's absolute value and range to `10^16` meters to prevent enormous finite inputs from overflowing preview calculations. This deliberately generous transport bound is not an EVE gameplay rule.
- Export observes the same limits as import. Oversized selections fail with guidance to copy fewer formations. Nothing is silently truncated or clamped.

Only formation names and probe geometry travel. No IDs, paths, account aliases, character names from metadata, timestamps, currently selected formation, temporary launched-probe positions, or credentials are included.

No compression, file picker, file export, author metadata, signatures, or clipboard-specific wrapper is included initially. The JSON is independent of the clipboard so a later file/library transport can reuse it.

## Architecture and ownership

- **Pure formation-sharing module under `wingman/evesettings/`:** owns the version-1 format, strict validation, explicit export projection, and conversion to/from the existing formation domain model. No file, clipboard, network, or global state access. Keep transport restrictions separate from the existing local-file reader so existing files are not newly rejected by unrelated operations.
- **Thin bridge methods in `wingman/ui/api.py`:** expose pure export and parse/validation operations. Sharing methods never accept destination paths or write settings. Python revalidates bridge inputs rather than trusting page controls. Existing formation save remains the sole persistence path for the draft.
- **`wingman/web/formations.js`:** owns copy selection, clipboard results, paste review, draft insertion, conflict feedback, and dirty/revision state. Page-owned UI state does not become persisted Python state.
- **Existing codec and writer:** used only when the user saves. Do not feed imported JSON directly into the settings codec; validated domain objects are written into the recipient's existing document.

The editor stores coordinates in km and ranges in AU. The portable format uses meters. Existing `fromMeters` rounds ranges to six decimal AU places, while positions are not deliberately rounded. The sharing conversion must preserve imported values without adding that rounding step; formatting a display value must not replace its stored number. Export is a snapshot of current editor values, not a promise of byte-identical recovery of the original `.dat`. Tests must distinguish ordinary floating-point unit-conversion tolerance from deliberate rounding. The ordinary post-save reload still uses the existing range normalization; acceptance checks must distinguish the values committed to disk from normalized editor display/state after reload. This release does not promise lossless raw-file editing, and must not broaden into changing unrelated local-file load semantics.

## Async and UI boundaries

- Import review captures the account path and draft revision. If either changes before candidates are added, refuse insertion and require review against the current draft again. Route exit cancels the review; a late validation response cannot reopen it or add data elsewhere.
- Disable starting Copy/Paste during account loading or saving. Do not disable Cancel or the ability to recover from a paste error. Delayed clipboard status must remain scoped to the originating operation rather than appearing on another account or route.
- A failed validation, canceled review, or stale response preserves the full prior draft. Addition is all-or-nothing in page state.
- Preserve the existing revision protections around save completion and post-save reload; importing is an edit and must advance that revision like ordinary editing.
- Stay inside the formation route. No new title-bar destination. Save remains the route's sole accent action; sharing controls are secondary.
- Follow `DESIGN.md`: page-owned dialogs, `.check` wrappers for copy selection, accessible labels, text-only rendering of user names, explicit hidden/display rules, visible keyboard focus, and focus restoration after dismissal.
- Review/paste layout must fit the 840x625 CSS floor and be walked in WebView2. No new framework or build step.

## Why existing selective copy is not the export implementation

`copy_selected` deliberately clones the entire source and restores excluded target groups. Unknown source data travels even when no offered groups are selected (`tests/test_evesettings_selective.py`). That is useful local-copy behavior, not a privacy boundary.

Sharing is allowlisted extraction: only explicitly supported data leaves the machine. Do not change existing local-copy behavior to implement this feature, and do not reuse its output as a share artifact.

Likewise, the sidecar's decode/encode consistency check is not proof that arbitrary third-party settings content is safe. Cross-player input is a new trust boundary. Version 1 handles only names and bounded numeric geometry.

## Verification and acceptance

Implementation must cover:

1. Export/parse round trips with multiple formations, Unicode names, fractional coordinates, unusual positive ranges, and different source/target local IDs.
2. Metadata omission, unsupported types/versions, unknown fields, duplicate JSON keys, strict numeric types, empty input, malformed/deeply nested JSON, non-finite/oversized numbers, and all size/count/name boundaries. Validation errors are contained and never partially import.
3. Case-insensitive name conflicts within an artifact and against a target draft; rename, cancel, and no-replacement behavior. A resolved review is validated again before addition.
4. Copy snapshots valid unsaved edits; only selected formations travel; clipboard success/failure accurately reported.
5. Review/add/cancel perform no file writes. Saving into a different account retains prior formations, existing IDs, scratch data, unrelated settings, and a valid prior EVE selection; imported IDs are minted locally.
6. Stale validation replies, account/route changes, and edits overlapping save completion do not discard drafts or insert into a different account.
7. Existing formation, codec, operations, API, bridge-contract and page-convention tests; full pytest and Ruff checks when implemented.
8. Manual browser and Windows/WebView2 checks: keyboard selection and paste, conflict correction, cancellation, denied clipboard, floor-size layout, save failures, and repeated copy/paste/save/reload.
9. Live EVE check with two unrelated accounts: export on one, import on the other, launch and verify formations plus existing selection, then restore the backup. Existing Python and lexical web tests do not prove this behavior.

## Deferred investigation

Before overview sharing, inspect representative real overview data, dependencies on other settings, embedded personal/identity values, and current EVE-native export/import interoperability. Do not infer a safe public schema from existing opaque selective-copy groups.

Before complete UI setups, establish supported window/tab/panel dependencies, account-to-character targeting, new-profile creation and selection workflow, and resolution/UI-scale handling. Chat associations, histories, hardware preferences, and ship-specific module arrangements remain excluded unless separately justified.

A library later distributes explicit local copies. No automatic preset synchronization or updates to installed settings. Public publishing, private corp permissions, authentication, moderation, hosting, and provenance policy are separate decisions.

## Design-phase evidence

- Read `PRODUCT.md`, `DESIGN.md`, the existing settings decode design, relevant source, and tests. A structured read-only discovery pass distinguished extractability from safe portability.
- On this design worktree, ran `uv sync --locked --extra dev`, then `uv run --no-sync python -m pytest tests/test_evesettings_formations.py tests/test_evesettings_selective.py tests/test_evesettings_codec.py tests/test_evesettings_ops.py -q`: **189 passed, 1 skipped**. The real-codec integration test is skipped because the bundled codec is absent.
- These are existing baseline tests, not verification of an implemented sharing feature. No browser, Windows/WebView2, live EVE, or cross-player exercise has been performed for this design.
