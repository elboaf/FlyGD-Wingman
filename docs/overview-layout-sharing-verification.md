# Overview/layout sharing: parser checkpoint

## Status and scope

**Tasks 1–3 of the [implementation plan](overview-layout-sharing-plan.md) are
implemented and independently reviewed. Task 4 is incomplete.** Its universal
development stop has been superseded by the
[case-based reassessment](overview-layout-sharing-reassessment.md): pure adapter
work may proceed while unproved mutations refuse locally. This is not a finished
setup-sharing feature or a release sign-off.

Implementation base: `4ecab11`. Verified code checkpoint: `904d1a8`.

| Commit | Result |
| --- | --- |
| `5a457d0` | Evidence map and independent synthetic source/recipient fixtures |
| `f5c04a5` | Strict portable semantic model and Wingman JSON transport |
| `67acc4a` | Bounded native YAML compatibility; repeated preset groups preserved |
| `904d1a8` | Native JSON scalar fidelity correction found during task review |

No settings-document adapter/writer, profile constructor, new controller
endpoints, GUI, launcher action or live-profile mutation has been implemented
in this checkpoint. Existing probe-sharing behavior remains separate. The branch
has not been pushed or offered for merge as a completed feature.

## What changed and how it works

- `setup_model.py` owns the semantic schema, supported settings/enums/windows,
  limits, new-copy normalization and review-summary projection. Ordered labels,
  exact names and all six geometry integers are retained. It has no file or
  application effects.
- `setup_sharing.py` checks the UTF-8 byte budget, decodes JSON strictly and
  rejects duplicate fields/nonstandard constants. A complete Wingman envelope
  receives full-model validation. Native JSON values go directly to native
  normalization, without reinterpretation through YAML. Canonical export checks
  its output structure and bytes after normalization, as well as its input.
- `overview_yaml.py` uses PyYAML's maintained SafeLoader with a bounded event
  preflight before construction. It rejects unsupported tags, aliases, anchors,
  documents, fields, shapes and duplicate keyed records. Native normalization
  uses the same partial overview model and never supplies a layout component.
- Native tabs become one primary group. Missing native options remain missing;
  supplied aggregates replace rather than imply a union. Ambiguous label types
  retain every record and set an explicit ambiguity flag. A future review/apply
  path must require **Keep my ship labels** before using such an input; the
  parser alone does not enforce a not-yet-implemented GUI action.
- Synthetic fixtures distinguish sender and recipient identities, settings,
  local preference bytes, labels, active groups and stale cached geometry.
  Their helpers retain real codec snapshot/revision/verification/publication
  operations while optionally substituting only subprocess transport.
- PyYAML 6.0.3 was added to the lock, with its complete installed MIT licence in
  the shipped notices. No unrelated dependency version was changed.

The [field map](ui-setup-field-map.md) separates measured representations,
declared Wingman policies, unsupported variants and unproved EVE semantics.
Raw private evidence is not committed. Synthetic transport round-trips are not
proof that EVE interprets the proposed result correctly.

## Discoveries and deliberate decisions

### Preserve repeated group entries

The authorized native export contains repeated group IDs in four of its 42
filter definitions: 37 additional entries. Task 2 initially rejected these,
although the synthetic fixture passed. Task 3 corrected that restriction for
preset `groups` only, in both native and portable input.

**Entries and order are preserved, not deduplicated.** Every entry still counts
toward list/node/byte budgets. Unique named definitions, tab IDs, assignments and
other keyed records remain unique; unrelated membership validation was not
weakened. This avoids silently changing supplied data to make a test pass.

The real input was checked in memory: 42 definitions, eight tabs, one normalized
native group, nine label records, ambiguity true, no layout, and exact group
sequences preserved. These are parser results, not native reset or application
results. No source names, IDs or label text entered the synthetic fixture.

### Keep JSON semantics on the native path

Task review found that decoding native JSON and then reparsing its text with
PyYAML changed some values. Scientific notation could become a string, and
escaped supplementary Unicode could become separate surrogate characters.

Two regression failures reproduced the issue. The fix passes already-decoded
JSON values into the shared native normalizer. Equivalent YAML/JSON cases now
preserve exact names/references and numeric values/types. This did not bypass
JSON duplicate/constant checks or either format's resource/domain validation.

### Presence and conservative support limits

Full Wingman settings normalize absent supported overrides to explicit null
(clear/reset intent); partial native settings retain omission. False and empty
aggregates are distinct from either. Optional label formatting retains its
supplied presence. Semantic boolean fields accept both boolean values, not
arbitrary integers; this does not establish their physical EVE representation.

This initial model requires a nonempty full tab/group configuration and nonempty
non-whitespace preset/tab names, without rewriting accepted text. RGB/RGBA
components use the observed normalized 0–1 domain. Non-null label font/colour
variants, unproved sentinels and other unsupported variants refuse rather than
being transformed or discarded. These are supported-subset limits, not EVE-wide
claims.

## Verification actually performed

The following fresh controller-run checks passed at `904d1a8`, after task-local
polish and the reviewed correction:

```bash
uv run --no-sync python -m pytest tests/ --basetemp=/tmp/wingman-setup-prefix-final -q -rs
# 7,569 passed, 41 skipped in 190.42s

uv run --no-sync ruff check .
# All checks passed

uv run --no-sync ruff format --check .
# 307 files already formatted

git diff 4ecab11..HEAD --check
# Passed
```

The 41 skips comprise **32 unavailable bundled-codec cases and nine Windows-only
cases**. They are not counted as passed. Earlier Task 1 verification exercised
all four new fixture documents through the existing native executable via the
test seam: the 19-test focused run passed, including those four native cases.
That does not replace the broader native/Windows CI prerequisites in Task 10.

Other recorded task evidence:

- Task 1: 15 preparatory tests passed plus four availability skips; native-enabled
  run 19 passed; full suite 6,890 passed/41 skipped.
- Task 2: behavioral RED, 520 new tests plus 450 probe-sharing regressions passed;
  full suite 7,410 passed/41 skipped. A separate RED caught canonical output
  expansion exceeding the node budget; export now checks the expanded result.
- Task 3: initial RED 57 failed/589 passed, then 646 passed. Repeated-group
  correction had its own RED (five failed/two passed) and GREEN (seven passed).
  Focused final checks: 719 passed/five skipped; full 7,539 passed/41 skipped.
- Review fix: two scalar-fidelity RED failures, then 10 passed. Broader checks:
  1,241 passed/five skipped; full 7,569 passed/41 skipped.
- Locked dependency sync, repository lint/format, installed PyYAML licence/version
  coverage and scoped diff checks passed. Task-local polish changes were inspected
  before fresh checks.

Each task received an independent cross-family spec/quality review. Task 1 and
Task 2 were approved without findings. Task 3's Important scalar-fidelity finding
was corrected and scoped re-review found it addressed with no new breakage.
There is no final whole-feature review or release approval yet.

No browser, real clipboard, Windows/WebView2, frozen-build or live EVE acceptance
was run for this parser checkpoint. No GUI exists for this phase yet. The earlier
sender-clone experiment is never a fresh-recipient baseline.

## Original reasons for stopping Task 4

The concerns below remain relevant, but treating them as a universal prerequisite
for all adapter development was too broad. The
[reassessment](overview-layout-sharing-reassessment.md) records newer controlled
evidence, corrects the domain explanation and defines supported versus refused
cases. It supersedes the blanket manual-test/development-stop instruction below;
that instruction is retained here as the historical checkpoint, not a new user
request.

The retained corpus does not establish safe behavior for:

1. **Protected/default definitions.** Repeated `DefaultPreset_*` names do not
   prove an exhaustive built-in classifier or safe collisions with custom names.
2. **Selected-tab and cache references.** Stored active selections, tab names,
   profile metadata and related caches have uncertain replacement/reset rules.
   Deleting containing sections or choosing arbitrary defaults is not justified.
3. **Retiring surplus overview windows.** Grouping, open/state maps, geometry and
   stack references interact. No proved recipe currently authorizes removing or
   resetting them in a recipient.

The next step needs a controlled, explicitly authorized EVE observation session:
a genuinely fresh initialized disposable recipient, a no-change startup/shutdown
control, then separate before/after/reload captures for default/custom filter,
selected-tab, rename/filter replacement and secondary-group retirement operations.
The operator drives EVE; the assistant must not silently change launcher selection,
clone sender DATs into the fresh recipient, delete caches or modify originals.
Exact steps should be agreed before new live-profile work.

Until those observations establish the affected rules, do not implement a guessed
writer or bypass the gate merely because pure parser tests pass. Tasks 4–11 remain
unfinished. The existing linked worktree and ignored per-plan ledger are retained
for resumption.

## Rulings made during this checkpoint

These decisions remain reviewable; none permits unproved profile writes.

1. Use the configured named implementation/review agents rather than override
   models contrary to the global routing agreement. If wrong, capability may
   require escalation/rework.
2. Treat fixture assertions as preparatory contracts, not product/EVE acceptance.
   If a fixture is wrong, downstream schema work needs correction; the physical
   proof gate and actual-EVE acceptance must remain independent.
3. Continue only pure model/parser Tasks 2–3 while physical behavior remains
   unproved. If later evidence differs, parser work may need revision, not a
   rollback of user settings.
4. Accept semantic true/false flags and preserve independently optional supported
   formatting fields without default-filling. An admitted semantic value may
   still need an adapter refusal or revision until its encoding is proved.
5. Normalize full absent settings to null while preserving partial omissions;
   reject null for non-nullable supplied native values. A finer source distinction
   may require later revision before publication.
6. Require nonempty full tabs/groups and meaningful names, with normalized 0–1
   colours. Legitimate edge cases outside this initial subset may be refused and
   need evidence-backed expansion.
7. Preserve repeated preset group entries exactly and narrowly correct the model
   restriction. Later physical handling may still need a documented refusal,
   but no supplied entries are silently removed.

## Reviewer focus and knowledge check

Review resource guarantees at the real decoding boundaries, optional/absent data,
ordered labels, repeated groups, canonical output expansion and native JSON
scalar fidelity. Keep the demonstrated portable model distinct from the still
unproved EVE adapter behavior.

1. Why does full missing-setting normalization differ from partial native input?
2. Why are repeated preset group entries retained while tab assignments stay unique?
3. Which guarantees apply before YAML construction versus after JSON decoding?
4. Why must successful JSON values bypass YAML reinterpretation?
5. What additional evidence is required before a new profile can be published?
