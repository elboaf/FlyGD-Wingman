# Saved Preview layouts — implementation evidence (#213)

Status: executing the approved spec and plan; no feature acceptance claimed.

- Spec: [preview-layouts-design.md](preview-layouts-design.md)
- Plan: [preview-layouts-plan.md](preview-layouts-plan.md)
- Worktree: `/mnt/c/dev/flygd-wingman/.worktrees/preview-layouts`
- Branch: `feature/preview-layouts`
- Starting plan revision: `ad7aa79764476f034a4923027ddca09e0e0629b1`
- Source base: `76afd3dc34f20eb071c97f25cd6d891ae11c352a`
- Per-task briefs/reports/reviews/ledger: ignored `.superpowers/sdd/preview-layouts-plan/`.

## Baseline

Before any source change, a dedicated environment was created with
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv sync --locked --extra dev`.
Node `v26.5.0` was present. The release codec was built from this checkout with
`cargo build --locked --release --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-layouts-codec`,
installed into this checkout's ignored `packaging/bin`, and
`codec.codec_available()` asserted true.

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-preview-layouts-baseline --junitxml=/tmp/wingman-preview-layouts-baseline.xml
```

Result: **12,502 passed, 13 Windows-only skips in 325.70s**. The skipped cases
require Windows junctions, DPAPI/WinDLL, native preview/message-pump APIs or the
Windows tray backend; no Node/codec prerequisites skipped. This is baseline
regression evidence, not proof of the proposed feature or Windows operator acceptance.

## Preflight ordering clarification

Task 2 must establish completion-bound ordinary visibility leases before Task 3
uses exclusive batches. Therefore the ordinary `refresh_primary_visibility`
primitive and shared `PrimaryLayoutLiveResult` record are introduced in Task 2;
Task 3 consumes the same interface and adds capture/apply records. This changes
internal task placement only, not product behavior or persisted schema.

## Task 1 — pure snapshots and lossless offline exclusions

Implemented only `SavedCharacter`, `SavedLayout` and the seven agreed pure model
functions in `preview/savedlayouts.py`; no native capture/commit/live-result types,
admission, controller, bridge actions or named-layout UI. Settings now defaults
`preview.saved_layouts` to an independent `{version: 1, items: []}` and normalizes
it on every write. Loading rejects malformed records whole, preserving valid
siblings and the working arrangement. Writes refuse malformed/duplicate proposals;
record revisions hash sorted-key JSON, independent of owner insertion order.

Snapshot owners use strict `crops.valid_owner` without casefolding. IDs remain
opaque nonempty strings like cycle-group IDs; later creation owns UUID generation.
Names are trimmed, nonblank and printable (control characters are refused even
at the ends). Geometry is strict signed-32-bit integers, positive dimensions,
and safe right/bottom arithmetic. Capture prefers actual live rectangles, then
retained `layout.Entry` geometry, then committed current geometry. Saved-only
owners contribute identity, not an older snapshot's geometry/visibility. Apply
validates first, preserves legacy geometry lock bits, changes only recorded
non-null rectangles and Preview choices, and retains absent owners unchanged.

Only `preview.excluded` passes `cap=None` to `roster.deserialize`; legacy roster
validation/deduplication is unchanged, and history/other policy caps remain 64.
`previews.js:rows()` now unions excluded-only owners through its existing
null-prototype map. The existing Node fixture proves a 65th excluded-only owner
and prototype-like names remain editable while Preview is Off, with the existing
inverted checkbox semantics. No markup, CSS, runtime or external resources changed.

### Task 1 verification

All Python/Ruff commands used
`UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync`.

- RED, before production edits: new model/settings files — **8 failed, 111 setup
  errors** (missing model/default, dropped `Pilot64`). Compatibility/page files —
  **3 failed, 86 passed** (missing default, capped exclusions, 64 rather than 67
  rows). The standalone roster `cap=None` characterization already passed because
  Python's old `out[:None]` slice was uncapped; the new annotation/branch makes
  that contract explicit without changing other callers.
- Initial required GREEN: **423 passed**. After self-polish/formatting, broader
  model, settings, layout/store/crop, committed reader, API field, bridge and
  packaging gates: **944 passed**. One earlier broader invocation used a nonexistent
  test filename and collected nothing; corrected to `test_api_settings_fields.py`.
- Ruff: initial test-only raw-regex/import-format findings corrected;
  `ruff check .` passed and `ruff format --check .` reported **442 files formatted**.
- `node scripts/js_smoke.js`: **PASS every page module loaded**.
- `cargo test --locked --offline --manifest-path packaging/settings-codec/Cargo.toml --target-dir /tmp/wingman-preview-layouts-codec`:
  **1 passed**, no network used.
- Full suite, run exactly once after Task 1 implementation:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-preview-layouts-venv uv run --no-sync python -m pytest tests/ -q -rs --basetemp=/tmp/wingman-preview-layouts-task1-full --junitxml=/tmp/wingman-preview-layouts-task1-full.xml
```

Result: **12,624 passed, 13 Windows-only skips in 307.18s**. No missing Node/codec
skips. Unique `/tmp/wingman-preview-layouts-task1-*` basetemps/logs retain RED,
GREEN, broader and full-run evidence. Detailed commands and self-review are in
the ignored task report; baseline/preflight contents above are preserved.

Self-review/polish was local only, as requested; no subagents, independent review,
network or GitHub operations. No unresolved Task 1 correctness finding. Native
ordering, browser rendering and Windows/WebView2/live-EVE acceptance remain for
later tasks/operator verification; these results do not establish them.
