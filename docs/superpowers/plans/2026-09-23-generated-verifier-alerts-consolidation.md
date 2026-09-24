# Generated-Verifier and Alerts Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the generated gap-verifier product from 35 identities to a mutation-qualified set of at least 22 and the Alerts top-anchor product from 31 identities to a mutation-qualified set of at least 24, with exact identity, skip, scope, and hosted evidence.

**Architecture:** Freeze the merged PR #286 baseline first, then qualify the generated and Alerts candidates independently with temporary production/helper mutants and supplemental fixture inputs that never survive a probe. Only after both mutation gates pass may `tests/test_shoot_screens.py` derive the retained parameter sequences; all other executable files remain byte-identical.

**Tech Stack:** Python 3.12, pytest, Node.js/CommonJS VM harnesses, generated ES5 screenshot verifier scripts, Cargo settings codec, uv, Git, GitHub Actions JUnit/timing artifacts.

**Spec:** `docs/superpowers/specs/2026-09-23-generated-verifier-alerts-consolidation-design.md`

## Global Constraints

- Source baseline is merged PR #286 at `8d5b9305` (`Consolidate current-owner lifecycle tests (#286)`).
- Design authority is `docs/ci-test-budget-redesign.md`; Stage 3 authorization and comparator evidence are in `docs/ci-current-owner-lifecycle-consolidation-results.md`.
- Committed executable changes are limited to parameter derivation in `tests/test_shoot_screens.py`.
- The only other committed paths are this plan, the approved Stage 3 spec, and `docs/ci-generated-verifier-alerts-consolidation-results.md`.
- `scripts/shoot_screens.py`, `tests/fixtures/screenshot_pages.cjs`, and `tests/fixtures/screenshot_alerts.cjs` may be mutated only as temporary, uncommitted probes and must be restored after every probe.
- Fixture-only mutants prove dispatch wiring only. They never qualify a production/helper branch and never justify an identity removal.
- Every mutant must fail at the intended assertion. A TypeError, timeout, worker crash, cleanup failure, protocol failure, or unrelated later assertion is not evidence.
- Retain all five generated settled cases, all five same-owner missing cases, all five same-owner wrong-text cases, one same-owner geometry witness per owner, all 15 Alerts base states, both Alerts missing short circuits, all three Alerts visibility mechanisms, both Alerts anchors, and all four Alerts edge comparisons unless the design is revised before implementation.
- The approved unexpanded candidate is `22 + 24 = 46` retained product identities, `220 / 90 / 91 / 101 = 502` four-file identities, 20 removals, and zero additions.
- The 46 and 502 counts are consequences, not deletion targets. A surviving or masked mutant expands the retained set; it never permits a compensating deletion.
- Node and the built release settings codec are required. A Node, codec, native-contract, or unexplained platform skip invalidates the relevant verification.
- No production behavior, screenshot scenario semantics, workflow, dependency, lockfile, packaging, marker, budget, shard, cadence, or overall-runtime claim is in scope.
- Stage 4 lower Fittings consolidation remains stopped.
- If an exact source anchor below differs, refuse the replacement, record the mismatch, and return to design review. Do not use a broader textual replacement.

## File Structure and Ownership

- Create `docs/ci-generated-verifier-alerts-consolidation-results.md` as the single evidence ledger: baseline inventories, comparator provenance, mutation rows, mappings, verification, hosted observations, deviations, and the bounded next decision.
- Modify `tests/test_shoot_screens.py` only in Task 4: named derived constants and the two target parametrization decorators.
- Temporarily modify and restore `scripts/shoot_screens.py` in Tasks 2–3: exact owner predicates, owner-to-helper wiring, shared visibility/geometry/hit-test branches, and Alerts guards.
- Temporarily modify and restore `tests/fixtures/screenshot_pages.cjs` in Task 2 only to isolate masked hidden, zero-height, point-specific, null-hit, and descendant-hit inputs alongside production/helper mutants.
- Temporarily modify and restore `tests/fixtures/screenshot_alerts.cjs` in Task 3 only when a narrow input is needed to isolate `parent.hidden`; this fixture is supplemental evidence only.
- Do not create a mutation runner, witness test module, helper script in the repository, or committed fixture scenario.

## Task Right-Sizing

1. Task 1 is a documentation-only baseline freeze that can be accepted without accepting any candidate deletion.
2. Task 2 qualifies the generated product and shared helper independently; a reviewer can reject its branch attribution without blocking review of the baseline.
3. Task 3 qualifies Alerts independently and consumes only the already-recorded shared-helper evidence.
4. Task 4 is the sole executable change and is forbidden until Tasks 2–3 are approved.
5. Task 5 proves the complete local endpoint without publication.
6. Task 6 performs final polish/review and, only after explicit authorization, publication and hosted comparison.

## Plan-Author Preflight — Completed Without Source Deletion

The plan author collected the exact current worktree and built the candidate in an untracked `/tmp` archive. No repository source or test identity was deleted or edited.

Baseline formula:

```python
all_nodes = collect(
    "tests/test_shoot_screens.py",
    "tests/test_new_screenshots.py",
    "tests/test_current_screenshots.py",
    "tests/test_fittings_page.py",
)
normalized_hash = sha256(("\n".join(all_nodes) + "\n").encode()).hexdigest()
```

Candidate generated formula:

```python
_GAP_CAPTURE_CASES = tuple(
    (scenario, key)
    for scenario in ("settled", "missing", "wrong-text")
    for key in GAP_CAPTURES
) + (
    ("hidden", "profiles-copy-scope"),
    ("clipped", "profiles-copy-scope"),
    ("clipped", "fittings-metadata-narrow"),
    ("clipped", "fittings-copy-preflight-bottom-narrow"),
    ("clipped", "fittings-copy-result-bottom-narrow"),
    ("covered", "fittings-copy-result-bottom-narrow"),
    ("zero-area", "settings-wanderer-controls-narrow"),
)
```

Candidate Alerts formula:

```python
_ALERTS_CAPTURE_SCENARIOS = (
    _ALERTS_BASE_SCENARIOS
    + _ALERTS_ANCHOR_SCENARIOS
    + _ALERTS_CLIPPED_SCENARIOS
)
```

Preflight results:

- Baseline counts: `240 / 90 / 91 / 101 = 522`, all unique.
- Baseline four-file hash: `07c1e080c24157001c3aa936ac7c26ec6307e9f246973cfb65f92164c31a51e6`.
- Baseline target products: 35 generated + 31 Alerts = 66 unique identities.
- Candidate generated count: 22.
- Candidate Alerts count: 24.
- Candidate retained-product hash: `359da2ca8f13df995ac43ed76bd0aa19ba75cb4ec3b1fe1e4fb6c8e6a38d71f9`.
- Candidate four-file counts: `220 / 90 / 91 / 101 = 502`.
- Candidate four-file hash from actual temporary collection: `592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a`.
- Exact projected diff: 20 removals, zero additions.
- The generated derived order intentionally moves the retained `wrong-text` block before the retained shared `hidden` witness; therefore the candidate four-file hash must come from actual candidate collection, not a naive set-filter of the 522-ID baseline.

---

### Task 1: Freeze the Exact PR #286 Baseline and Comparator Controls

**Files:**
- Create: `docs/ci-generated-verifier-alerts-consolidation-results.md`
- Read: `docs/ci-current-owner-lifecycle-consolidation-results.md`
- Read artifacts: `/tmp/wingman-pr286-windows/{pytest-result.xml,pytest-timing.json}`
- Read artifacts: `/tmp/wingman-pr286-ubuntu/{pytest-result.xml,pytest-timing.json}`
- Test/collect: the four screenshot test files and the two target products in `tests/test_shoot_screens.py`

**Interfaces:**
- Consumes: baseline commit `8d5b9305`, complete PR #286 artifacts, current `GAP_CAPTURES` insertion order, and existing Alerts parametrization order.
- Produces: an authoritative 522-ID baseline, 66-ID product baseline, normalized hashes, exact hosted skip tuples, comparator provenance, and timing controls used by Tasks 2–6.

**Independent deliverable:** A reviewer can verify the source and hosted baseline without accepting any mutation result or executable change.

- [ ] **Step 1: Verify checkout identity and prerequisites**

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-generated-verifier-alerts-consolidation
git status --short --branch
git merge-base --is-ancestor 8d5b9305 HEAD
node --version
uv sync --locked --extra dev
```

Expected: the branch contains `8d5b9305`, has only the approved Stage 3 design/plan history before Task 1, Node is available, and dependency sync succeeds.

- [ ] **Step 2: Collect the complete baseline and both products without deleting cases**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py tests/test_new_screenshots.py \
  tests/test_current_screenshots.py tests/test_fittings_page.py \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-stage3-before-all.txt
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing \
  tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-stage3-before-products.txt
```

Run a Python audit that keeps lines beginning with `tests/`, preserves collection order, joins with `\n`, includes the final newline, and asserts:

```python
assert counts == {
    "tests/test_shoot_screens.py": 240,
    "tests/test_new_screenshots.py": 90,
    "tests/test_current_screenshots.py": 91,
    "tests/test_fittings_page.py": 101,
}
assert len(all_nodes) == len(set(all_nodes)) == 522
assert len(product_nodes) == len(set(product_nodes)) == 66
assert sha256(("\n".join(all_nodes) + "\n").encode()).hexdigest() == (
    "07c1e080c24157001c3aa936ac7c26ec6307e9f246973cfb65f92164c31a51e6"
)
```

Expected: exact baseline formulas and hashes match the approved design. Save the complete 522-ID and 66-ID ordered lists in the results document.

- [ ] **Step 3: Recompute the approved candidate in memory and in a temporary archive**

Use the exact formulas in the plan-author preflight. First assert in memory that the retained product is 22 generated + 24 Alerts and that all retained IDs exist in the 66-ID baseline. Then create an untracked temporary archive, apply the exact Task 4 derivation there, collect it, and assert:

```python
assert candidate_counts == (220, 90, 91, 101)
assert len(candidate_all) == len(set(candidate_all)) == 502
assert len(candidate_products) == len(set(candidate_products)) == 46
assert candidate_product_hash == "359da2ca8f13df995ac43ed76bd0aa19ba75cb4ec3b1fe1e4fb6c8e6a38d71f9"
assert candidate_four_file_hash == "592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a"
assert len(set(all_nodes) - set(candidate_all)) == 20
assert not (set(candidate_all) - set(all_nodes))
```

Expected: the candidate projection matches the design. Delete only the temporary archive after recording its command/output; do not edit or delete any worktree test case.

- [ ] **Step 4: Freeze exact PR #286 provenance and artifact integrity**

Record:

- PR #286 run `35882408360`.
- Branch head `0c785ce18193b5900f8d810a8a4dc7e0f10c9f1e`.
- Synthetic merge `c1ab289e4fdd31e7cc5be2c8322a2557c48e1a26`.
- Base `459c5d6b57f5f35c97d3076bee25a6f65ba515be`.
- Checks job `107253913132`.
- Ubuntu job `107253913433`.
- Windows job `107253913529`.
- Artifact roots `/tmp/wingman-pr286-ubuntu` and `/tmp/wingman-pr286-windows`.
- Each root contains `pytest-result.xml` and `pytest-timing.json`.

Recheck the GitHub job API and checkout logs if the artifacts or provenance differ. Expected: all three jobs concluded successfully and checked out the exact synthetic merge above.

- [ ] **Step 5: Publish the full comparator skip tuples**

Parse every `<testcase>` with `<skipped>` from both PR #286 JUnit files. Normalize only path separators and generated `pytest-of-*/pytest-N/<temporary-leaf>` fragments to `<PYTEST_TMP>`. Store every ordered `(test identity, normalized skip reason)` tuple in the results document.

Expected:

- Windows: 67 exact tuples.
- Ubuntu: 14 exact tuples.
- No failure or error.
- No Node or settings-codec availability skip.
- The 14 Ubuntu tuples include exactly the platform-only cases already listed in `docs/ci-current-owner-lifecycle-consolidation-results.md`.

- [ ] **Step 6: Freeze target timing controls without making a timing claim**

Parse JUnit testcase sums and timing JSON, and record these PR #286 observations:

| Platform | Generated 35 | Alerts 31 | Combined 66 | `test_shoot_screens.py` | Four-file target | All cases | Test step / job |
|---|---:|---:|---:|---:|---:|---:|---:|
| Windows | 6.155s | 3.552s | 9.707s | 30.799s / 240 | 90.316s / 522 | 656.277s | 11m38s / 12m34s |
| Ubuntu | 4.923s | 2.454s | 7.377s | 23.304s / 240 | 71.268s / 522 | 341.717s | 6m15s / 6m54s |

Also record the structural process control: generated cases use the persistent screenshot worker, while each Alerts case launches `screenshot_alerts.cjs`; the approved candidate projects 35 to 28 structural starts solely because seven Alerts identities are removed. State explicitly that these are controls and observations, not speedup claims.

- [ ] **Step 7: Create the results document with complete, reviewable sections**

Create these exact top-level sections and populate Task 1 evidence now:

1. `Scope and authority`
2. `Task status`
3. `Exact 522-ID baseline inventory`
4. `Exact 66-ID product baseline`
5. `Approved candidate projection`
6. `PR #286 comparator provenance and artifacts`
7. `Complete normalized comparator skip tuples`
8. `Comparator timing controls`
9. `Generated mutation ledger`
10. `Alerts mutation ledger`
11. `Parameter derivation and 20-row mapping`
12. `Local verification`
13. `Hosted evidence`
14. `Deviations, expansions, and concerns`
15. `Required self-review`

Later-task rows use explicit status such as `NOT STARTED — Task 2 owns this evidence`; do not use unresolved placeholder markers or abbreviated future-work text.

- [ ] **Step 8: Audit scope and commit**

```bash
git diff --check
git diff --name-only
git add docs/ci-generated-verifier-alerts-consolidation-results.md
git commit -m "docs: freeze generated verifier alerts baseline"
```

Expected: only the new results document is committed in Task 1.

**Implementer report:** Provide the commit SHA; exact 522/66 counts and hashes; artifact paths; 67/14 skip counts; timing-control table; changed paths; and any discrepancy. State that no case was deleted and no executable file changed.

**Fresh reviewer gate:** A fresh reviewer independently reparses the two collection files and both comparator artifact sets, confirms all IDs/hashes/skip tuples/provenance, checks the timing table arithmetic, and approves the Task 1 commit before Task 2 begins.

**Fix loop:** For any mismatch, stop. Correct collection normalization or artifact attribution, rerun the complete Task 1 audit, add a follow-up documentation fix commit, and repeat fresh review. Do not reinterpret a mismatch as harmless drift.

---

### Task 2: Qualify the Generated 22-Case Candidate and Shared Helper

**Files:**
- Modify: `docs/ci-generated-verifier-alerts-consolidation-results.md`
- Temporarily modify and restore: `scripts/shoot_screens.py:1161-1192,1196-1353`
- Temporarily modify and restore: `tests/fixtures/screenshot_pages.cjs:576-780`
- Test: generated 35-case product, the unchanged 13-case geometry matrix, dedicated owner tests, gap walk tests, persistent-worker protocol, and isolation tests in `tests/test_shoot_screens.py`

**Interfaces:**
- Consumes: Task 1's exact baseline and candidate IDs.
- Produces: a branch-level mutation ledger proving every retained generated semantic/wiring/shared-helper witness, or an explicit expansion/redesign decision before any deletion.

**Independent deliverable:** Documentation-only qualification evidence; no production, helper, fixture, or test witness survives.

#### Exact probe discipline

For every row below:

1. Run the named witness green with unmodified source.
2. Apply only the exact candidate replacement.
3. Run the named witness and require the intended assertion/location.
4. Save stdout/stderr and the exact diff in the results document.
5. Restore by exact inverse replacement.
6. Require `git diff --exit-code -- scripts/shoot_screens.py tests/fixtures/screenshot_pages.cjs` before the next row.

If the before text does not match exactly once, refuse the mutant. If the test fails by TypeError, timeout, protocol error, worker crash, or a different assertion, mark it unqualified.

- [ ] **Step 1: Run the complete future-retained generated set and unchanged geometry matrix green**

Run all 22 candidate IDs plus:

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests \
  tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts \
  tests/test_shoot_screens.py::test_profiles_scope_capture_uses_actual_capability_without_overrides \
  tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes \
  tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer \
  tests/test_shoot_screens.py::test_lower_result_capture_keeps_recovery_before_pairs_not_sticky \
  tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details -q
```

Expected: all selected cases pass before mutation.

- [ ] **Step 2: Qualify every owner anchor's absence and exact text**

Use these exact candidate source anchors. Each absence mutant may change multiple clauses only when every clause is part of the same named anchor-existence chain; it must leave route, owner, unrelated semantics, and shared helper behavior intact.

| Owner | Temporary absence-chain replacements | Temporary wrong-text replacement | Required retained witness |
|---|---|---|---|
| Wanderer | `&& text(remove, 'Remove connection') && !remove.disabled` → `&& (!remove || (text(remove, 'Remove connection') && !remove.disabled))`; `[note, test, remove]` → `[note, test].concat(remove ? [remove] : [])` | `text(remove, 'Remove connection')` → `remove && remove.textContent.length > 0` | same-owner `missing-settings-wanderer-controls-narrow`; `wrong-text-settings-wanderer-controls-narrow` |
| Profiles | Apply the four exact healthy-branch replacements immediately below this table | `text(note, 'Checked groups are copied as a unit. Unchecked groups stay unchanged. Everything else is copied.')` → `note && note.textContent.length > 0` | same-owner `missing-profiles-copy-scope`; `wrong-text-profiles-copy-scope` |
| Metadata | `&& text(save, 'Save') && save.disabled && discard` → `&& (!save || (text(save, 'Save') && save.disabled)) && discard`; final exposed list `[summary, nameLabel, name, descriptionLabel, description, save]` → `[summary, nameLabel, name, descriptionLabel, description].concat(save ? [save] : [])` | `text(save, 'Save')` → `save && save.textContent.length > 0` | same-owner `missing-fittings-metadata-narrow`; `wrong-text-fittings-metadata-narrow` |
| Preflight | `&& text(note, 'Enter an alternate name or select Skip for each conflict before reviewing changes.')` → `&& (!note || text(note, 'Enter an alternate name or select Skip for each conflict before reviewing changes.'))`; `review.getAttribute('aria-describedby') === note.id` → `(!note || review.getAttribute('aria-describedby') === note.id)`; `note.scrollIntoView({block: 'end', behavior: 'instant'});` → `if (note) note.scrollIntoView({block: 'end', behavior: 'instant'});`; `check(exposed(note, pane) &&` → `check((!note || exposed(note, pane)) &&` | the exact `text(note, 'Enter an alternate name or select Skip for each conflict before reviewing changes.')` call → `note && note.textContent.length > 0` | same-owner `missing-fittings-copy-preflight-bottom-narrow`; `wrong-text-fittings-copy-preflight-bottom-narrow` |
| Result | `&& text(status, 'Not attempted: rate limit') && status.classList.contains(expected.status)` → `&& (!status || (text(status, 'Not attempted: rate limit') && status.classList.contains(expected.status)))`; `var requiredNodes = [name, character, status, disclosure];` → `var requiredNodes = [name, character, disclosure]; if (status) requiredNodes.splice(2, 0, status);` | `text(status, 'Not attempted: rate limit')` → `status && status.textContent.length > 0` | same-owner `missing-fittings-copy-result-bottom-narrow`; `wrong-text-fittings-copy-result-bottom-narrow` |

For the Profiles absence probe, apply these exact four replacements together; they weaken only the healthy `es-copy-scope-note` existence chain:

```javascript
// 1
&& visible(WM.el('es-copy-options')) && visible(note) && scope && commit);
// becomes
&& visible(WM.el('es-copy-options')) && (!note || visible(note)) && scope && commit);

// 2
check(text(note, 'Checked groups are copied as a unit. Unchecked groups stay unchanged. Everything else is copied.')
  && !note.classList.contains('warn') && commit.hidden && WM.el('es-copy-scope-summary').textContent);
// becomes
check(!note || (text(note, 'Checked groups are copied as a unit. Unchecked groups stay unchanged. Everything else is copied.')
  && !note.classList.contains('warn') && commit.hidden && WM.el('es-copy-scope-summary').textContent));

// 3
note.scrollIntoView({block: 'center', behavior: 'instant'});
// becomes
if (note) note.scrollIntoView({block: 'center', behavior: 'instant'});

// 4
check(exposed(note, pane));
// becomes
check(!note || exposed(note, pane));
```

Expected intended failure for each negative witness: the fixture reaches `assert.throws(verify, /Screenshot content did not settle/, scenario)` and reports that the expected screenshot-settle exception was not thrown. The witness must not fail from a null dereference.

Record ten rows: exact mutation, exact retained ID, assertion, exit status, restoration command/result. Settled cases are green controls only and do not count as sensitivity evidence.

- [ ] **Step 3: Qualify owner-to-`exposed()` wiring independently**

Apply one exact mutation at a time:

| Owner | Exact before | Temporary replacement | Required same-owner geometry witness |
|---|---|---|---|
| Wanderer | `[note, test, remove]` | `[note, test]` | `zero-area-settings-wanderer-controls-narrow` |
| Profiles | `check(exposed(note, pane));` | `check(true);` | `clipped-profiles-copy-scope` |
| Metadata | `[summary, nameLabel, name, descriptionLabel, description, save]` | `[summary, nameLabel, name, descriptionLabel, description]` | `clipped-fittings-metadata-narrow` |
| Preflight | `check(exposed(note, pane) &&` | `check(` | `clipped-fittings-copy-preflight-bottom-narrow` |
| Result | `var requiredNodes = [name, character, status, disclosure];` | `var requiredNodes = [name, character, disclosure];` | `clipped-fittings-copy-result-bottom-narrow` |

Expected: each retained geometry witness fails at the fixture's `assert.throws` because the mutated generated verifier wrongly accepts the damaged exact anchor. For Result, confirm the clipped target is `status`, not the broad covered target or disclosure.

- [ ] **Step 4: Qualify hidden and positive-area branches**

Use these exact shared-helper mutations:

```javascript
// hidden branch
if (parent.hidden || window.getComputedStyle(parent).visibility === 'hidden') return false;
// becomes
if (window.getComputedStyle(parent).visibility === 'hidden') return false;

// width branch
if (r.width <= 0 || r.height <= 0
// becomes
if (r.height <= 0

// height branch
if (r.width <= 0 || r.height <= 0
// becomes
if (r.width <= 0
```

Witnesses and supplemental fixture inputs:

- Hidden: run `hidden-profiles-copy-scope`. Because the DOM double's `getClientRects()` also rejects `hidden`, temporarily change only `if (node.hidden) return [];` to `if (node.hidden && scenario !== 'hidden') return [];`. With original production the case must still pass as a negative because `parent.hidden` rejects it; with the production hidden mutant it must fail at `assert.throws`. Restore both files. Fixture-only failure is not evidence.
- Width: `zero-area-settings-wanderer-controls-narrow` must kill removal of `r.width <= 0`.
- Height: for the same retained zero-area ID, temporarily replace the exact fixture line:

```javascript
const r = rect(120, 130, zero && this === target ? 120 : 760, 330);
```

with:

```javascript
const r = zero && this === target
  ? rect(120, 130, 760, 130)
  : rect(120, 130, 760, 330);
```

Original production must reject the zero-height target; after removal of `r.height <= 0`, the retained ID must fail at `assert.throws`. Restore the fixture before recording the production mutant as qualified. The shared no-client-rect branch is qualified separately by Task 3's retained `display-none-master` production witness.

- [ ] **Step 5: Qualify all four containment edges and one-pixel tolerance**

Mutate each exact clause independently:

```javascript
r.left < Math.max(0, p.left) - tolerance
r.right > Math.min(innerWidth, p.right) + tolerance
r.top < Math.max(0, p.top) - tolerance
r.bottom > Math.min(innerHeight, p.bottom) + tolerance
```

Remove only the named clause and run the matching unchanged geometry identity:

- left → `overflow-left`;
- right → `overflow-right`;
- top → `overflow-top`;
- bottom → `overflow-bottom`.

Then change `var tolerance = 1;` to `var tolerance = 1.01;` and run all four `overflow-*` cases. Expected: the matching negative case is wrongly accepted and fails at `assert.throws`; all `rounding-*` and `edge-*` controls remain green with original production.

The retained `clipped-fittings-copy-preflight-bottom-narrow` is the product-level clipped witness; the 13-case matrix owns exact edge/tolerance attribution.

- [ ] **Step 6: Qualify all five hit-test points and `.every()`**

The exact production point list is:

```javascript
[[r.left + inset, r.top + inset], [r.right - inset, r.top + inset],
  [r.left + inset, r.bottom - inset], [r.right - inset, r.bottom - inset],
  [(r.left + r.right) / 2, (r.top + r.bottom) / 2]].every(function (point) {
```

For each point index 0 through 4, replace the exact fixture line:

```javascript
document.elementFromPoint = () => covered && (scenario !== 'covered-summary' || measured === target)
  ? document.body : measured;
```

with this temporary index-specific form for the first probe:

```javascript
let hitIndex = 0;
document.elementFromPoint = () => {
  const pointIndex = hitIndex++ % 5;
  return covered && pointIndex === 0 ? document.body : measured;
};
```

Repeat the exact replacement four more times with the equality integer changed to `1`, `2`, `3`, and `4` respectively.

Then:

1. Verify original production rejects the retained `covered-fittings-copy-result-bottom-narrow` input.
2. Temporarily remove only that coordinate from the production array.
3. Rerun the retained covered result ID; expected failure is the fixture `assert.throws` because the verifier now accepts the omitted covered point.
4. Restore both files.

Then keep one point covered and replace `.every(function (point) {` with `.some(function (point) {`. Expected: the retained covered result ID kills the mutant at `assert.throws`. A broad all-points-covered input alone cannot qualify `.every()` because `.some()` would still return false.

- [ ] **Step 7: Qualify null-hit, unrelated-hit, direct-node, and descendant handling**

Apply one exact production mutation at a time to:

```javascript
return hit && (hit === node || node.contains(hit));
```

| Dimension | Temporary replacement | Input/witness | Intended result |
|---|---|---|---|
| Null refusal | `return !hit || (hit === node || node.contains(hit));` | For `covered-fittings-copy-result-bottom-narrow`, use `let hitIndex = 0; document.elementFromPoint = () => { const pointIndex = hitIndex++ % 5; return covered && pointIndex === 0 ? null : measured; };` | Original rejects the null first point after damage; mutant accepts it; fixture `assert.throws` fails |
| Unrelated covered hit | `return Boolean(hit);` | Existing retained `covered-fittings-copy-result-bottom-narrow` | Mutant accepts `document.body`; fixture `assert.throws` fails |
| Direct-node equality | `return hit && hit !== node && node.contains(hit);` | `settled-fittings-copy-result-bottom-narrow` with the existing direct `measured === node` hits | Positive case fails in the final required-node exposure check |
| Descendant acceptance | `return hit && hit === node;` | For `settled-fittings-copy-result-bottom-narrow`, replace the exact fixture callback with `const descendantHit = WM.make('span'); target.appendChild(descendantHit); document.elementFromPoint = () => measured === target ? descendantHit : measured;` | Original positive passes; mutant fails in the final required-node exposure check |

The supplemental fixture must not alter target text, ownership, geometry, or other hit points. Restore it after each probe.

- [ ] **Step 8: Build the complete 13-removal generated ledger**

For each removed generated ID, record:

1. same-owner semantic evidence: exact missing and wrong-text retained IDs and their owner predicate mutants;
2. same-owner geometry/wiring evidence: exact retained geometry ID and wiring mutant;
3. shared branch evidence: hidden, edge/tolerance, covered/hit-test, or width/height mutant and witness;
4. intended assertion text/location;
5. exact restoration proof.

Use the approved 13-row mapping from the spec without abbreviating owner labels to family-level claims.

- [ ] **Step 9: Apply the expansion/redesign protocol before any implementation**

If a mutant survives or is masked:

- stop Task 2;
- leave `tests/test_shoot_screens.py` unchanged;
- restore every temporary file and prove empty diffs;
- add the smallest existing generated identity that kills the exact branch if one exists;
- otherwise revise the spec, this plan, and the results document before implementation;
- recalculate the actual retained product inventory, four-file inventory, mappings, counts, and hashes;
- never delete a different case to preserve 22 or 502;
- if persistent fixture/test-support/production change is required, return to design review rather than expanding scope.

- [ ] **Step 10: Re-run green generated/protocol/isolation coverage and commit documentation only**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_capture_worker_reuses_process_and_preserves_business_outcomes \
  tests/test_shoot_screens.py::test_gap_capture_worker_vm_failures_preserve_stack_and_recover \
  tests/test_shoot_screens.py::test_gap_capture_worker_is_order_independent \
  tests/test_shoot_screens.py::test_gap_capture_worker_cancels_pending_timer \
  tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing \
  tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests \
  tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture -q
git diff --exit-code -- scripts/shoot_screens.py tests/fixtures/screenshot_pages.cjs
git diff --check
git add docs/ci-generated-verifier-alerts-consolidation-results.md
git commit -m "docs: qualify generated verifier alert mutations"
```

Expected before reduction: complete 35-case generated product and 13-case geometry matrix pass; no witness code remains; only the results document is committed.

**Implementer report:** Provide the commit SHA; every mutation row and intended assertion; restoration proof count; generated candidate status (`QUALIFIED`, `EXPANDED`, or `REDESIGN REQUIRED`); actual retained IDs/hashes if expanded; and exact changed paths.

**Fresh reviewer gate:** A fresh reviewer checks every exact before/replacement pair against source, verifies failures are at intended assertions, confirms fixture inputs are supplemental, audits all 13 mappings, and proves no temporary diff remains.

**Fix loop:** Any rejected row is unqualified. Restore source, narrow or replace the probe without broadening scope, rerun the row and all affected green controls, commit corrected documentation as a follow-up, and repeat fresh review. Do not proceed to Task 3 with an unresolved shared-helper dimension.

---

### Task 3: Qualify the Alerts 24-Case Candidate

**Files:**
- Modify: `docs/ci-generated-verifier-alerts-consolidation-results.md`
- Temporarily modify and restore: `scripts/shoot_screens.py:1161-1192,2004-2028`
- Temporarily modify and restore: `tests/fixtures/screenshot_alerts.cjs:1-130`
- Test: Alerts 31-case product, Alerts walk test, and Task 2's unchanged shared geometry matrix

**Interfaces:**
- Consumes: Task 2's qualified shared-helper ledger for positive area, clipping tolerance, and hit testing.
- Produces: independent master/health guards, both missing short circuits, all three visibility mechanisms, all four edge comparisons, exact seven-row mapping, or an explicit expansion/redesign stop.

**Independent deliverable:** Documentation-only Alerts qualification; no fixture or generated script change survives.

- [ ] **Step 1: Run all 24 future-retained Alerts cases and shared controls green**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions \
  tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure \
  tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests -q
```

Expected before reduction: 31 Alerts product cases, two walk cases, and 13 geometry cases pass.

- [ ] **Step 2: Qualify the independent master and health missing guards**

Master exact mutation:

```javascript
if (!visible(master) || !exposed(master.closest('label.check'), pane)) {
// becomes
if (master && (!visible(master) || !exposed(master.closest('label.check'), pane))) {
```

Run `missing-master`. Expected: the mutated setup no longer throws the master-specific framing error, so `assert.throws(run, /Screenshot.*settings-alerts/, scenario + ' must refuse a misleading capture')` fails. It must not fail with `master.closest` TypeError.

Health exact mutation:

```javascript
if (!health || !health.textContent.trim() || !exposed(health, pane)) {
// becomes
if (health && (!health.textContent.trim() || !exposed(health, pane))) {
```

Run `missing-health`. Expected: the same fixture assertion fails because the missing health short circuit was independently weakened.

Restore and diff-audit after each probe.

- [ ] **Step 3: Qualify all three Alerts visibility mechanisms**

Use exact production/helper mutations:

| Mechanism | Exact temporary mutation | Retained ID | Supplemental fixture rule |
|---|---|---|---|
| `hidden` ancestry | remove only `parent.hidden ||` from the shared `visible()` loop | `hidden-master` | Temporarily change `if (node.hidden || node.style.display === 'none') return [];` to `if ((node.hidden && scenario !== 'hidden-master') || node.style.display === 'none') return [];`. Original production must still reject via `parent.hidden`; the mutant must be accepted and fail at `assert.throws`. |
| computed visibility | `if (parent.hidden || window.getComputedStyle(parent).visibility === 'hidden')` → `if (parent.hidden)` | `invisible-health` | None; computed visibility is the only intended rejecting branch. |
| no client rect/display none | `if (!node || !node.getClientRects().length)` → `if (!node)` | `display-none-master` | None; fixture display-none wiring is supplemental, and production `getClientRects` rejection must be the killed branch. |

A fixture-only failure or a later generic error does not qualify the branch. Restore both files after hidden-master before continuing.

- [ ] **Step 4: Qualify all four exact Alerts edge comparisons**

Remove one shared-helper comparison at a time and run its pairwise retained ID:

- top clause → `clipped-master-top`;
- right clause → `clipped-master-right`;
- bottom clause → `clipped-health-bottom`;
- left clause → `clipped-health-left`.

Expected: each mutated setup accepts its clipped anchor, so the fixture's exact negative `assert.throws` fails. A different edge case or the other owner cannot substitute for the named branch.

- [ ] **Step 5: Confirm positive-area and hit-test attribution without adding Alerts cases**

Record that:

- `zero-health` remains among the 15 unshrunk base states and exercises an Alerts owner with zero width;
- Task 2's width and temporary zero-height production mutants are killed by retained/shared generated witnesses;
- Task 2's five-point, `.every`, null, unrelated, direct-node, and descendant production mutants are killed by the retained covered Result/shared geometry evidence;
- `document.elementFromPoint = () => measured` in the Alerts fixture is wiring context only and is not counted as production hit-test sensitivity.

If an Alerts-specific production path bypasses the shared helper or any shared branch evidence does not execute the same `_framed_content_script()`, stop and redesign. Do not add a fixture-only claim.

- [ ] **Step 6: Preserve and audit all 15 base invariants**

Run the complete 15-state base sequence and the two walk cases. Confirm the unchanged fixture assertions still own:

- action-free staging;
- route, section, pane, and card ownership;
- outer Settings scroll reset and section-scroll preservation;
- master preference and Advanced disclosure preservation;
- no anchor `scrollIntoView`;
- setup-before-capture order and fail-closed walk behavior.

No base state may be removed or remapped to an anchor-product case.

- [ ] **Step 7: Build the complete seven-removal Alerts ledger**

Record these exact rows:

| Removed | Owner witness | Mechanism/edge witness |
|---|---|---|
| `hidden-health` | `invisible-health`, `missing-health` | `hidden-master` |
| `invisible-master` | `hidden-master`, `display-none-master` | `invisible-health` |
| `display-none-health` | `invisible-health`, `missing-health` | `display-none-master` |
| `clipped-master-bottom` | `clipped-master-top`, `clipped-master-right` | `clipped-health-bottom` |
| `clipped-master-left` | `clipped-master-top`, `clipped-master-right` | `clipped-health-left` |
| `clipped-health-top` | `clipped-health-bottom`, `clipped-health-left` | `clipped-master-top` |
| `clipped-health-right` | `clipped-health-bottom`, `clipped-health-left` | `clipped-master-right` |

Each row also names the exact production mutant, intended fixture assertion, and restoration proof.

- [ ] **Step 8: Apply the stop/redesign protocol for any masked Alerts branch**

If either guard, any visibility mechanism, or any edge mutant survives or fails for the wrong reason:

- stop before Task 4;
- restore all temporary files;
- expand the retained Alerts set only with the smallest existing case that kills the exact branch;
- revise the spec, this plan, and results before implementation;
- recalculate product/four-file inventories, hashes, mappings, and structural start count;
- do not preserve 24 or 502 by deleting another case;
- if persistent fixture/helper/test-support change is required, return to design review.

- [ ] **Step 9: Re-run complete Alerts/shared green coverage and commit documentation only**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions \
  tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure \
  tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests -q
git diff --exit-code -- scripts/shoot_screens.py tests/fixtures/screenshot_alerts.cjs
git diff --check
git add docs/ci-generated-verifier-alerts-consolidation-results.md
git commit -m "docs: qualify Alerts anchor mutations"
```

Expected before reduction: 31 Alerts cases, two walk cases, and 13 geometry cases pass; no temporary change remains.

**Implementer report:** Provide the commit SHA; guard, visibility, edge, base-invariant, and shared-helper evidence; seven-row mapping; restoration proof; candidate status; and any expansion with recalculated identities/hashes.

**Fresh reviewer gate:** A fresh reviewer verifies independent short circuits, production rather than fixture sensitivity, exact edge ownership, all base-state invariants, the seven mappings, and empty temporary diffs.

**Fix loop:** Any masked or misattributed branch returns to the Task 3 stop protocol. Correct/revise, rerun all affected controls, add a follow-up documentation fix commit, and repeat fresh review. Task 4 cannot begin until both Task 2 and Task 3 are approved.

---

### Task 4: Derive and Apply the Qualified Parameter Selection

**Files:**
- Modify: `tests/test_shoot_screens.py:154-160,773-781,2568-2600`
- Modify: `docs/ci-generated-verifier-alerts-consolidation-results.md`
- Do not modify: `scripts/shoot_screens.py`, either screenshot fixture, or any other test module

**Interfaces:**
- Consumes: approved Task 2 and Task 3 mutation ledgers and their actual qualified retained sets.
- Produces: named, derived generated and Alerts parameter sequences; exactly 20 removals and zero additions for the unexpanded candidate; complete 13+7 mapping.

**Independent deliverable:** The only executable commit, reviewable as parameter derivation after prior mutation qualification.

- [ ] **Step 1: Enforce the prior-gate precondition**

Read the results document and assert both product statuses are `QUALIFIED` or an approved documented `EXPANDED` set exists. Require empty diffs for scripts and fixtures.

```bash
git diff --exit-code -- scripts/shoot_screens.py \
  tests/fixtures/screenshot_pages.cjs tests/fixtures/screenshot_alerts.cjs
```

Expected: no temporary mutation remains. Refuse implementation if either ledger is incomplete.

- [ ] **Step 2: Write collection-level red assertions before changing decorators**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing \
  tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-stage3-products-before-reduction.txt
python - <<'PY'
from pathlib import Path
nodes = [line for line in Path('/tmp/wingman-stage3-products-before-reduction.txt').read_text().splitlines()
         if line.startswith('tests/')]
assert len(nodes) == 46, f'expected qualified 46, still collected {len(nodes)}'
PY
```

Expected for the unexpanded approved candidate: FAIL with 66 collected. If qualification expanded the set, substitute the documented actual expected count; do not use 46.

- [ ] **Step 3: Add the exact generated derived constant**

Immediately after `GAP_CAPTURES`, add:

```python
_GAP_CAPTURE_CASES = tuple(
    (scenario, key)
    for scenario in ("settled", "missing", "wrong-text")
    for key in GAP_CAPTURES
) + (
    ("hidden", "profiles-copy-scope"),
    ("clipped", "profiles-copy-scope"),
    ("clipped", "fittings-metadata-narrow"),
    ("clipped", "fittings-copy-preflight-bottom-narrow"),
    ("clipped", "fittings-copy-result-bottom-narrow"),
    ("covered", "fittings-copy-result-bottom-narrow"),
    ("zero-area", "settings-wanderer-controls-narrow"),
)
```

Replace the two stacked decorators with:

```python
@pytest.mark.parametrize(("scenario", "key"), _GAP_CAPTURE_CASES)
```

Do not hand-copy the five settled/missing/wrong-text keys. Preserve IDs as `scenario-key`.

If qualification expanded the generated set, add only the approved extra tuples after the seven witnesses and document their order.

- [ ] **Step 4: Add the exact Alerts named groups**

Immediately before the Alerts test, add:

```python
_ALERTS_BASE_SCENARIOS = (
    "settled-disabled",
    "settled-enabled",
    "wrong-route",
    "wrong-section",
    "inactive-route",
    "inactive-section",
    "missing-section",
    "missing-pane",
    "hidden-section",
    "hidden-pane",
    "hidden-card",
    "wrong-owner",
    "empty-health",
    "zero-health",
    "outside-viewport",
)
_ALERTS_ANCHOR_SCENARIOS = (
    "missing-master",
    "missing-health",
    "hidden-master",
    "invisible-health",
    "display-none-master",
)
_ALERTS_CLIPPED_SCENARIOS = (
    "clipped-master-top",
    "clipped-master-right",
    "clipped-health-bottom",
    "clipped-health-left",
)
_ALERTS_CAPTURE_SCENARIOS = (
    _ALERTS_BASE_SCENARIOS
    + _ALERTS_ANCHOR_SCENARIOS
    + _ALERTS_CLIPPED_SCENARIOS
)
```

Replace the inline list-comprehension decorator with:

```python
@pytest.mark.parametrize("scenario", _ALERTS_CAPTURE_SCENARIOS)
```

If qualification expanded Alerts, add only the approved identities to the corresponding named group and recalculate all evidence.

- [ ] **Step 5: Prove exact product order, IDs, and hashes green**

Collect the two products and assert the exact ordered generated and Alerts ID lists from the spec. For the unexpanded candidate assert:

```python
assert len(generated) == len(set(generated)) == 22
assert len(alerts) == len(set(alerts)) == 24
assert sha256(("\n".join(generated + alerts) + "\n").encode()).hexdigest() == (
    "359da2ca8f13df995ac43ed76bd0aa19ba75cb4ec3b1fe1e4fb6c8e6a38d71f9"
)
```

Then run both products:

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing \
  tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions -q
```

Expected: 46 passed if unexpanded.

- [ ] **Step 6: Prove exact four-file collection and set diff**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py tests/test_new_screenshots.py \
  tests/test_current_screenshots.py tests/test_fittings_page.py \
  --collect-only -q -p no:cacheprovider > /tmp/wingman-stage3-after-all.txt
```

Audit against Task 1's baseline. For the unexpanded candidate require:

```python
assert counts == (220, 90, 91, 101)
assert len(after) == len(set(after)) == 502
assert len(set(before) - set(after)) == 20
assert not (set(after) - set(before))
assert after_hash == "592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a"
```

Expected removals are exactly the 13 generated and seven Alerts IDs in the approved mapping tables. No script or fixture identity is added.

- [ ] **Step 7: Publish the complete 20-row mapping and after inventories**

In the results document add:

- complete ordered 502-ID after inventory;
- complete ordered 46-ID retained product inventory;
- normalized hashes;
- exact set diff;
- all 13 generated mapping rows with semantic + wiring + shared branch evidence;
- all seven Alerts mapping rows with owner + mechanism/edge evidence;
- explicit zero-addition proof;
- actual expansion explanation if applicable.

- [ ] **Step 8: Run the affected file and commit**

```bash
uv run --no-sync python -m pytest tests/test_shoot_screens.py -q
git diff --check
git diff --name-only
git add tests/test_shoot_screens.py \
  docs/ci-generated-verifier-alerts-consolidation-results.md
git commit -m "test: consolidate generated verifier alerts matrix"
```

Expected unexpanded result: `tests/test_shoot_screens.py` collects and passes 220 tests; only the target test file and results document are committed.

**Implementer report:** Provide the commit SHA; exact constants and order; product/four-file counts and hashes; 20 removals/zero additions; whole-file result; changed paths; and confirmation that mutation qualification preceded deletion.

**Fresh reviewer gate:** A fresh reviewer compares the diff to the approved candidate, derives all IDs from constants, verifies complete mappings and hashes, and confirms no test body, scenario semantics, script, fixture, or other module changed.

**Fix loop:** Any ID/order/hash/mapping/scope mismatch blocks Task 5. Correct only parameter derivation or the results evidence, rerun all Task 4 collection/execution checks, add a follow-up fix commit, and repeat fresh review. A mutation-related correction returns to Tasks 2–3 rather than being patched here.

---

### Task 5: Prove the Complete Local Endpoint

**Files:**
- Modify: `docs/ci-generated-verifier-alerts-consolidation-results.md`
- Verify only: all repository paths

**Interfaces:**
- Consumes: Task 4's executable endpoint and all frozen before/after inventories.
- Produces: five-order execution evidence, focused 502-case JUnit/timing, complete pytest/skip audit, independent gates, exact scope proof, and a clean locally reviewable branch.

**Independent deliverable:** Complete local evidence with no publication or hosted claim.

- [ ] **Step 1: Re-audit exact inventories and hashes from fresh collection**

Repeat Task 4's collection from scratch. Expected unexpanded endpoint:

- generated 22;
- Alerts 24;
- retained product 46 with hash `359da2ca8f13df995ac43ed76bd0aa19ba75cb4ec3b1fe1e4fb6c8e6a38d71f9`;
- `220 / 90 / 91 / 101 = 502`;
- four-file hash `592c3cd0c7d93d595b25eeb04d7d5adf2029bfeb8de6695f2ddc68d8eb37aa3a`;
- exactly 20 mapped removals and zero additions.

If the candidate expanded, use the published actual values and prove them instead.

- [ ] **Step 2: Run the exact focused mutation-owned families**

```bash
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py::test_gap_capture_worker_reuses_process_and_preserves_business_outcomes \
  tests/test_shoot_screens.py::test_gap_capture_worker_vm_failures_preserve_stack_and_recover \
  tests/test_shoot_screens.py::test_gap_capture_worker_is_order_independent \
  tests/test_shoot_screens.py::test_gap_capture_worker_cancels_pending_timer \
  tests/test_shoot_screens.py::test_gap_capture_requires_semantic_content_after_framing \
  tests/test_shoot_screens.py::test_gap_geometry_allows_only_one_pixel_rounding_and_still_hit_tests \
  tests/test_shoot_screens.py::test_metadata_capture_waits_for_real_detail_without_creating_drafts \
  tests/test_shoot_screens.py::test_profiles_scope_capture_uses_actual_capability_without_overrides \
  tests/test_shoot_screens.py::test_lower_copy_capture_rejects_unsettled_or_wrong_outcomes \
  tests/test_shoot_screens.py::test_lower_copy_capture_requires_retained_context_and_footer \
  tests/test_shoot_screens.py::test_lower_result_capture_keeps_recovery_before_pairs_not_sticky \
  tests/test_shoot_screens.py::test_copy_capture_rejects_stale_context_progress_and_technical_details \
  tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture \
  tests/test_shoot_screens.py::test_alerts_base_capture_requires_top_anchors_without_actions \
  tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure -q
```

Expected: all focused generated, shared-geometry, Alerts, walk, worker-protocol, and isolation tests pass.

- [ ] **Step 3: Run the four files in five exact orders**

Build ordered node arrays from the fresh 502-ID inventory and execute with Python `subprocess.run([...])`, passing every explicit node as its own argument:

1. normal file order;
2. reverse file order, preserving collection order within each file;
3. explicit forward node order;
4. explicit reverse node order;
5. deterministic shuffled node order with integer seed `0x8d5b9305`.

Expected: 502 passed in every order if unexpanded. Record each exact node-order SHA-256 and pytest result. Normal-file and forward-node hashes equal the published after hash; the other three hashes are computed and published from their actual order.

- [ ] **Step 4: Build/install the release codec and run focused four-file JUnit**

```bash
cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available()"
uv run --no-sync python -m pytest \
  tests/test_shoot_screens.py tests/test_new_screenshots.py \
  tests/test_current_screenshots.py tests/test_fittings_page.py \
  -q -rs --durations=50 \
  --junitxml=/tmp/wingman-stage3-focused.xml
```

Expected unexpanded endpoint: 502 passed, zero skipped/failures/errors. Record per-file, generated-product, Alerts-product, retained-product, removed-ID projection, and four-file testcase sums as observations.

- [ ] **Step 5: Run complete pytest with strict skip audit**

```bash
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/wingman-stage3-full.xml
```

Projection for the unchanged local environment and unexpanded candidate: baseline `16,611 - 20 = 16,591` passed, the same 14 intentional platform-only skips, and 16,605 JUnit cases. Treat this as an identity projection to audit, not a substitute for actual collection. If environment collection changes, explain and audit it before accepting; do not hardcode the projection over actual evidence.

Reject any Node, codec, native-contract, or unexplained new skip. Publish every actual `(identity, reason)` tuple and compare it with Task 1's local baseline list.

- [ ] **Step 6: Run independent gates**

```bash
node scripts/js_smoke.js
node --test tests/fixtures/screenshot_dom.test.cjs
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
git diff --check
```

Expected:

- JS smoke passes;
- Node DOM: 35 passed, zero failed/skipped/cancelled/todo;
- Cargo: one passed;
- Ruff check and format pass;
- diff check is empty.

- [ ] **Step 7: Audit whole-branch scope and temporary-mutant restoration**

```bash
python - <<'PY'
import subprocess
allowed = {
    'docs/ci-generated-verifier-alerts-consolidation-results.md',
    'docs/superpowers/plans/2026-09-23-generated-verifier-alerts-consolidation.md',
    'docs/superpowers/specs/2026-09-23-generated-verifier-alerts-consolidation-design.md',
    'tests/test_shoot_screens.py',
}
changed = set(subprocess.check_output(
    ['git', 'diff', '--name-only', '8d5b9305..HEAD'], text=True
).splitlines())
assert changed <= allowed, sorted(changed - allowed)
assert 'tests/test_shoot_screens.py' in changed
print('\n'.join(sorted(changed)))
PY
git diff --name-only 8d5b9305..HEAD -- \
  wingman .github scripts tests/fixtures packaging pyproject.toml uv.lock
```

Expected: changed paths are within the four-path allowlist; protected-path output is empty. Explicitly search changed paths for mutation markers, witness comments, debug output, and unresolved placeholder markers.

- [ ] **Step 8: Complete local results, self-review, and commit**

Record exact inventories/hashes, five order runs, focused/full counts and skips, independent gates, scope audit, structural process counts, and no timing claim. Complete the spec's self-review categories: placeholder, arithmetic, identity, mutation, scope, protected paths, claim discipline, and staged boundary.

```bash
git add docs/ci-generated-verifier-alerts-consolidation-results.md
git commit -m "docs: record generated verifier alerts verification"
git status --short --branch
```

Expected: clean branch after a documentation-only Task 5 commit.

**Implementer report:** Provide commit SHA; exact local commands/results; actual full count and complete skip audit; all five order hashes; focused/product/four-file sums; scope output; and remaining risks. Do not state a speedup.

**Fresh reviewer gate:** A fresh reviewer reruns inventory/hash/scope scripts, inspects JUnit and skip tuples, checks all arithmetic and mappings, and verifies the branch contains no temporary witness or protected-path change.

**Fix loop:** Any failure returns to its owning task. Mutation evidence returns to Tasks 2–3; identity derivation to Task 4; environment/gate/scope evidence to Task 5. Apply the smallest correction, rerun all affected and endpoint checks, add a follow-up commit, and repeat fresh review.

---

### Task 6: Final Polish, Independent Review, Authorized Publication, and Hosted Evidence

**Files:**
- Modify: `docs/ci-generated-verifier-alerts-consolidation-results.md`
- Review: approved spec, this plan, complete `8d5b9305..HEAD` diff, Task 5 JUnit/timing evidence, and PR #286 comparator artifacts

**Interfaces:**
- Consumes: the clean locally verified endpoint.
- Produces: polished/reviewed branch; only with explicit authorization, a PR and hosted Windows/Ubuntu artifact comparison to PR #286; bounded next decision.

**Independent deliverable:** Final review is separable from publication. No push or PR occurs without explicit authorization.

- [ ] **Step 1: Run `polish-core --fix` over the whole Stage 3 branch**

Load the `polish-core` skill and run its fix workflow for `8d5b9305..HEAD`. Inspect every edit. Reject any change outside the approved four-path allowlist or any edit that weakens evidence. Rerun every affected test/gate and commit only high-confidence corrections as a separate fix commit.

Expected: no unreviewed polish change remains.

- [ ] **Step 2: Obtain an independent whole-branch review**

A fresh reviewer examines:

- spec-to-plan-to-results coverage;
- exact mutation branch attribution and intended assertions;
- fixture-only evidence labels;
- expansion/stopping protocol;
- complete 20-row mapping;
- parameter derivation and ID order;
- full inventories/hashes/skips;
- protected-path and claim discipline;
- no lower Fittings/workflow/budget/shard scope.

Resolve every Critical or Important finding. Re-run affected tests and obtain fresh approval after each fix wave.

- [ ] **Step 3: Run fresh final local verification on the reviewed executable head**

At minimum rerun:

- fresh 502-ID collection and both hashes;
- the focused mutation-owned command;
- the complete four-file JUnit run;
- full pytest with skip audit;
- JS smoke;
- Node DOM 35;
- Cargo;
- Ruff check and format;
- diff/scope/protected-path audits;
- `git diff --check`.

Expected unexpanded endpoint remains `220 / 90 / 91 / 101 = 502`, 20 removals, zero additions, and the qualified hashes. Record the exact reviewed executable head SHA.

- [ ] **Step 4: Run `change-explainer` before publication**

Load the `change-explainer` skill and produce the reviewer-facing summary from the final diff, results, tests, and verification. The explanation must cover what changed, mutation gates, exact identity transformation, deviations/expansions, edge cases, verification actually run, reviewer focus, and remaining risks. It must state no Stage 3 or overall timing claim.

- [ ] **Step 5: Stop for explicit publication authorization**

Present the reviewed head SHA, clean status, exact counts/hashes, local gates, independent review outcome, and proposed PR title/body. Do not push, open a PR, or call GitHub mutation APIs until the maintainer explicitly authorizes publication.

- [ ] **Step 6: After authorization, publish the exact reviewed head**

Push the Stage 3 branch to `fork` and open a PR against `elboaf/FlyGD-Wingman:main` using `-R elboaf/FlyGD-Wingman`. Suggested title:

```text
Consolidate generated verifier and Alerts tests
```

The PR body states:

- qualified generated `35 → 22` and Alerts `31 → 24`, or actual expanded values;
- `522 → 502`, 20 removals, zero additions, or actual expanded values;
- mutation qualification and restoration boundaries;
- complete local evidence;
- structural process-start observation only;
- no workflow, budget, shard, overall-runtime, speedup, or lower Fittings claim.

- [ ] **Step 7: Record exact Stage 3 hosted provenance**

For the executable run record:

- PR number and run ID;
- exact branch head;
- exact synthetic merge;
- exact base;
- checks, Ubuntu, and Windows job IDs;
- checkout-log proof for the synthetic merge in every job;
- downloaded Windows/Ubuntu artifact paths containing `pytest-result.xml` and `pytest-timing.json`.

All required jobs must pass. If the base moved, record it explicitly; do not pretend PR #286 and Stage 3 share a base.

- [ ] **Step 8: Compare hosted artifacts directly with PR #286 run `35882408360`**

Parse both Stage 3 platform artifacts and `/tmp/wingman-pr286-{windows,ubuntu}`. Require:

- Windows and Ubuntu Stage 3 full testcase identity sets are equal;
- both Stage 3 target sets equal the published after inventory;
- exact target counts are `220 / 90 / 91 / 101 = 502` if unexpanded;
- relative to PR #286, exactly the published 20 identities are absent and zero are added;
- normalized Windows skip tuple set equals PR #286's 67 tuples;
- normalized Ubuntu skip tuple set equals PR #286's 14 tuples;
- no failure, error, Node skip, codec skip, or unexplained availability skip;
- generated, Alerts, combined-product, per-file, four-file, and all-case testcase sums are reported;
- removed-ID and common-retained-ID sums are decomposed where artifacts permit;
- pytest Test-step and job durations are reported only as observations.

For unchanged-workflow/target controls, compare Git blobs between PR #286 executable head and Stage 3 executable head. Authorized difference is only `tests/test_shoot_screens.py` plus documentation; `.github/workflows/ci.yml`, scripts, fixtures, other target files, dependencies, and packaging must remain byte-identical or the timing comparison is inconclusive.

Hosted pass projections for an unchanged environment are derived, not blindly hardcoded: Ubuntu baseline `16,611` passed minus 20 gives 16,591 with 14 skips; Windows baseline `16,558` passed minus 20 gives 16,538 with 67 skips. If actual platform collection differs, audit exact identities/reasons before any conclusion.

- [ ] **Step 9: Make the bounded next decision**

Decision rules:

- **GO for review of a separate later tranche only** if required jobs pass, platform identities/skips agree, exact removals/zero additions hold, mutation/scope contracts remain intact, and there is no unexplained material target regression.
- **INCONCLUSIVE** if provenance, blobs, artifacts, platform identities, or observations are not comparable; repeat measurement rather than infer.
- **STOP / repair** for contract failure, identity/skip divergence, residual mutation, protected-path drift, or unexplained material target regression.

No outcome authorizes workflow selection, budget enforcement, sharding, cadence changes, dependency changes, an overall/Stage 3 speedup claim, or lower Fittings work.

- [ ] **Step 10: Commit hosted evidence and verify the evidence head**

Commit only the results document:

```bash
git add docs/ci-generated-verifier-alerts-consolidation-results.md
git commit -m "docs: record hosted generated verifier alerts evidence"
```

After authorization, push the evidence commit, update the PR body with bounded conclusions, and wait for required checks on the exact documentation head. Finish only when those checks pass or the results document records an explicit unresolved status.

**Implementer report:** Provide polish edits, independent review outcome, final executable/evidence SHAs, publication authorization, PR/run/job provenance, artifact paths, identity/skip comparisons, all testcase sums, Test-step/job observations, decision, and remaining risks.

**Fresh reviewer gate:** A fresh reviewer validates the final diff and every hosted claim directly from APIs/logs/artifacts, confirms the comparator is PR #286 executable run `35882408360`, and checks the decision language for prohibited claims.

**Fix loop:** For code/test findings, return to the owning earlier task, rerun local verification, repolish, rereview, and obtain a new executable run. For evidence-only errors, correct the results document, reparse artifacts, commit a follow-up documentation fix, and re-run evidence-head checks. Never conceal an incomparable run with a timing conclusion.

---

## Plan Completion Self-Review

Before treating this plan as executable, the plan author performs these checks:

- [x] **Spec coverage:** Every authority, candidate ID, mutation family, mapping, stopping rule, verification gate, hosted comparator requirement, claim restriction, and Stage 4 stop has an owning task.
- [x] **Placeholder scan:** The plan contains no unresolved placeholder marker or abbreviated future-work text.
- [x] **Type/name consistency:** `_GAP_CAPTURE_CASES`, `_ALERTS_BASE_SCENARIOS`, `_ALERTS_ANCHOR_SCENARIOS`, `_ALERTS_CLIPPED_SCENARIOS`, and `_ALERTS_CAPTURE_SCENARIOS` are spelled identically in all tasks and match their parametrization decorators.
- [x] **Arithmetic consistency:** `35 + 31 = 66`, `22 + 24 = 46`, `13 + 7 = 20`, `240 - 20 = 220`, `220 + 90 + 91 + 101 = 502`, and local baseline `16,611 - 20 = 16,591` are consistent as projections for the unexpanded candidate.
- [x] **Mutation consistency:** Every temporary production/helper mutant has an intended retained witness, exact assertion, and restoration gate; supplemental fixture input is never credited alone.
- [x] **Scope consistency:** The only planned executable diff is `tests/test_shoot_screens.py`; scripts, fixtures, production, workflows, configuration, dependencies, packaging, markers, budgets, and shards remain protected.
- [x] **Claim discipline:** Structural process counts and durations are observations only; no Stage 3, whole-suite, job, runner-efficiency, or critical-path speedup is claimed.

## Execution Handoff

Plan complete at `docs/superpowers/plans/2026-09-23-generated-verifier-alerts-consolidation.md`.

Recommended execution: **Subagent-Driven Development** with a fresh implementer and fresh reviewer gate per task, using `superpowers:subagent-driven-development`. Inline execution is acceptable only with `superpowers:executing-plans` and the same task/commit/review boundaries.
