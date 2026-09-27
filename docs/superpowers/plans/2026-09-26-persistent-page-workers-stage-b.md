# Persistent Page Workers — Stage B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not dispatch subagents unless the maintainer separately authorizes them.

**Goal:** Replace 165 one-shot Node launches in four page-test families with four isolated session workers, build the 55 saved-layout main rows from one detached production receipt, and preserve every approved business contract.

**Architecture:** One hardened CommonJS host reads the six existing fixture programs and `screenshot_dom.cjs` as primitive UTF-8 source at startup, then executes the selected program through VM-owned CommonJS facades in a fresh realm for every request. Four module-local session fixtures retain only one `NodeScenarioWorker` process per family; the saved-layout module additionally owns one process-local, once-built, detached real receipt shared with the qualification module. Protocol failures destroy the process, business failures remain detached and recoverable in the same process, and raw JUnit `stage_b.*` properties are the authoritative worker/fsync evidence.

**Tech Stack:** Python 3.11, pytest 9, Node.js 26, CommonJS, `node:vm`, primitive NDJSON, `NodeScenarioWorker`, stdlib JSON/hash/XML/subprocess tooling, uv, Ruff, Cargo, and GitHub Actions JUnit artifacts.

**Spec:** `docs/superpowers/specs/2026-09-26-persistent-page-workers-stage-b-design.md`

## Global Constraints

- The source baseline is merged `main` commit `203d2068787cb3457916db6005afda0a7ce7a43a` (`Remove deterministic waste from Windows CI tests (#291)`).
- Preserve all 205 existing target identities, their order, names, parameters, markers, assertions, scenario matrices, and literal timeouts. Their ordered final-newline SHA-256 stays `7337d36844ca94b21a0af2c4568ede5828f81df882d2899ca28aa9a505b69343`.
- Preserve all 165 Node-owning identities and exact family/program/protocol mapping from the approved spec. Their ordered final-newline SHA-256 stays `60a253410671d0ac475c414940f007943ff96f4faebc30f0f1aaef9009e549fc`.
- Preserve all 12 current `NodeScenarioWorker` identities. Add exactly one helper-contract identity and exactly seven Stage B qualification identities: `217 + 8 = 225` implementation-relevant identities and `16,609 + 8 = 16,617` complete-suite outcomes.
- Expected complete Linux outcome is exactly `16,603 passed + 14 skipped = 16,617`. The later hosted Windows expectation is separately `16,550 passed + 67 skipped = 16,617`.
- A healthy 165-row run starts exactly four Node processes with request counts `62/65/17/21`; qualification starts and deliberate restarts are reported separately.
- Retain request timeouts exactly: saved layouts `25.0`, Fleet Sharing `20.0`, group backward `30.0`, and label markers `30.0` seconds.
- Retain direct one-shot execution of all six existing CJS paths with their positional argv, failure exits, stdout/stderr roles, and exact PASS terminals. The persistent host never replaces those CLIs.
- Every worker request owns a fresh VM realm, VM-created DOM, VM-owned CommonJS module and limited `require`, VM promises/errors/assertions/callbacks/listeners/timers, and freshly decoded input/markup. Only primitive source, markup, hashes, labels, and JSON text survive requests.
- The persistent host must not `require()` or cache-evict any of the six target fixtures or `tests/fixtures/screenshot_dom.cjs`; no target path may occur in `require.cache` or `module.children` before or after requests.
- Request cleanup completes before reply publication. A valid `ok:false` business result keeps the process; malformed startup/NDJSON/schema/family/protocol/scenario, timeout, process death, serialization failure, double completion, or failed cleanup emits no valid success and destroys the process.
- `NodeScenarioWorker` changes only in `_validate_reply`: first prove every required key is present without indexing any field, then require exact integer `id` (never `bool`) and exact integer-or-float, finite, nonnegative `duration_ms` (never `bool`). Every missing/type/range/nonfinite violation raises `_ProtocolError`, so the existing `missing-fields` case and every numeric defect retain the same discard/restart path. All lifecycle, timeout, discard, restart, close, stderr-tail, and late-exit behavior remains unchanged.
- Build the saved-layout receipt exactly once, through production `Api`/controller/store/settings/atomicio behavior. It has exactly 22 ordered values, costs exactly 19 fsync calls, is detached before restoration, and is decoded afresh for each of 55 main rows.
- Healthy fsync acceptance is exact: Node-owning 165 rows `1,059 -> 33`, all 205 existing rows `1,088 -> 62`; qualification/helper/probe overhead is separate.
- Raw JUnit properties, not terminal prints, are authoritative. Each `(exact node ID, property name)` has one owner and one value; duplicate identical values are still failures.
- Node on `PATH` and the built release settings codec in `packaging/bin` are mandatory for complete-suite evidence. A Node, codec, target, qualification, or unexpected native-availability skip is a stopping failure.
- No production, web, workflow, dependency, lockfile, configuration, packaging, cadence, marker, timeout, or Stage C change is allowed.
- Timing values are single-run observations only. Do not claim speedup, slowdown, lower bound, p95, runner efficiency, throughput, job impact, or critical-path causation.
- The user authorized versioning the Stage B spec, plan, results, and evidence. This does not authorize a push, PR, workflow dispatch, rerun, or hosted artifact collection from an unspecified run.
- Every temporary edit runs in disposable space or a bounded restoration wrapper and proves original bytes, SHA-256, binary diff, and NUL-delimited porcelain status in `finally`.
- One immutable 71-recipe registry is the sole mutation authority. Tasks 3/4/5 reference its canonical names only; each recipe owns phase, typed probe kind, exact pytest IDs or non-pytest labels, one unique literal sentinel and anchored regex, kind-appropriate forbidden masking, match-once edits, and mutated/restored probes. The one property-cardinality recipe owns both missing and duplicate-identical variants internally.
- TDD RED must collect the intended IDs and fail in the call phase at its unique assertion. Undefined imports, a missing worker file, collection/setup errors, skips, timeouts, or later generic failures do not count as RED.
- Task 1 materializes and runs collection/JUnit parsing first, freezes the actual 217-ID baseline, and binds `BASELINE_COLLECTED_IDS` before it imports or runs registry/restoration tooling. Its registry run is metadata/owner/schema smoke only; real edit qualification begins after each implementation phase exists.
- Task 1 also freezes the exact expected Task 2 relevant-225 and complete-16,617 orders. Task 2 compares fresh actual collections byte-for-byte with those expected files; Task 5 compares final collection byte-for-byte with the frozen actual Task 2 order.
- Every intermediate implementation commit is green for its changed component and all already-converted consumers.

---

## Exact File Structure and Ownership

The entire final range from `203d2068` is exactly these 17 paths:

| Path | Action and single responsibility |
|---|---|
| `docs/superpowers/specs/2026-09-26-persistent-page-workers-stage-b-design.md` | Approved immutable design authority; only evidence/status wording may be updated after implementation review. |
| `docs/superpowers/plans/2026-09-26-persistent-page-workers-stage-b.md` | This executable task sequence and final execution status. |
| `docs/ci-persistent-page-workers-stage-b-results.md` | Baseline, RED/GREEN, mutation, local, review, and later hosted evidence ledger. |
| `tests/test_preview_savedlayouts_page.py` | Saved-family session worker, manifest, once-provider/receipt fixture, 62 migrated requests, per-case evidence. |
| `tests/test_fleetsharing_hydration.py` | Fleet Sharing session worker, manifest, 65 migrated requests, diagnostics/evidence. |
| `tests/test_preview_group_backward.py` | Group-backward session worker, manifest, 17 migrated requests, diagnostics/evidence; 39 Python/API rows stay behaviorally unchanged. |
| `tests/test_preview_labelmarkers_page.py` | Label-marker session worker, manifest, 21 migrated requests and evidence. |
| `tests/fixtures/preview_savedlayouts.cjs` | Direct CLI plus VM-evaluable saved-main/saved-owner completion export; scenario assertions stay authoritative. |
| `tests/fixtures/preview_capture_sessions.cjs` | Direct CLI plus VM-evaluable saved-capture completion export. |
| `tests/fixtures/preview_dev_capture.cjs` | Direct CLI plus VM-evaluable saved-dev completion export and exact dev diagnostics. |
| `tests/fixtures/fleetsharing_page.cjs` | Direct CLI plus VM-evaluable Fleet Sharing completion export and controlled-error diagnostics. |
| `tests/fixtures/preview_group_backward.cjs` | Direct CLI plus VM-evaluable group-backward completion export, including the 144 inner dialog combinations. |
| `tests/fixtures/preview_labelmarkers.cjs` | Direct CLI plus VM-evaluable label-marker completion export. |
| `tests/fixtures/page_scenario_worker.cjs` | New shared startup validation, source-text registry, strict protocol, fresh VM/bootstrap/adapters, virtual scheduler, rejection mailbox, cleanup, diagnostics, and NDJSON server. |
| `tests/test_persistent_page_workers.py` | New seven-ID runtime/source/CLI/receipt qualification suite and qualification-only evidence helpers. |
| `tests/node_scenario_worker.py` | Numeric reply-schema hardening only. |
| `tests/test_node_scenario_worker.py` | One new non-parametrized numeric-schema/discard/restart contract ID. |

Read-only implementation authorities include `tests/html_tree.py`,
`tests/fixtures/screenshot_dom.cjs`, `tests/fixtures/screenshot_pages.cjs`,
`tests/fixtures/current_screenshot_pages.cjs`, `tests/test_api.py`,
`tests/test_preview_owner_eligibility.py`, `tests/test_api_fleetsharing.py`,
`tests/fleetsharing_capacity_helpers.py`, `wingman/ui/api.py`,
`wingman/settings.py`, `wingman/paths.py`, `wingman/atomicio.py`, and
`wingman/preview/{layout.py,layoutcontroller.py,savedlayouts.py}`.

### Exact permitted test-signature substitutions

No existing `test_*` signature may change except these six fixture substitutions; decorators and parameter lists remain byte-for-AST equivalent:

```text
test_saved_layout_page_ordering:
  (tmp_path, scenario, monkeypatch)
  -> (saved_layout_page_worker, saved_layout_receipt_bytes, request, scenario)

test_displayed_owner_controls_use_real_api_receipts:
  (tmp_path, source)
  -> (tmp_path, saved_layout_page_worker, request, source)

test_capture_session_page_ordering:
  (tmp_path, scenario)
  -> (tmp_path, saved_layout_page_worker, request, scenario)

test_sharing_watch_runtime:
  (tmp_path, scenario)
  -> (tmp_path, fleetsharing_page_worker, request, scenario)

test_group_backward_page:
  (tmp_path, scenario)
  -> (group_backward_page_worker, request, scenario)

test_marker_page_ownership:
  (tmp_path, scenario)
  -> (labelmarkers_page_worker, request, scenario)
```

New fixtures/helpers are not test functions and do not add identities. The one
non-Node Fleet Sharing ID and 39 non-Node group-backward IDs keep their original
signatures.

### Frozen family and CLI contract

| Family | Existing IDs | Program/protocol requests | Label form | Timeout | Exact output |
|---|---:|---|---|---:|---|
| `saved-layouts` | 62 | 55 `preview_savedlayouts.cjs` / `saved-main`; 3 same program / `saved-owner`; 3 `preview_capture_sessions.cjs` / `saved-capture`; 1 `preview_dev_capture.cjs` / `saved-dev` | `preview-saved-layouts/page/<scenario>`, `/owners/<source>`, `/capture/<scenario>`, `/dev/dev` | 25 | `PASS <scenario>`, owner `PASS owner-controls`, dev `PASS dev` |
| `fleet-sharing` | 65 | `fleetsharing_page.cjs` / `fleet-sharing` | `fleet-sharing/page/<scenario>` | 20 | `PASS <scenario>` |
| `group-backward` | 17 | `preview_group_backward.cjs` / `group-backward` | `preview-group-backward/page/<scenario>` | 30 | `PASS group backward <scenario>` |
| `label-markers` | 21 | `preview_labelmarkers.cjs` / `label-markers` | `preview-label-markers/page/<scenario>` | 30 | `PASS marker page <scenario>` |

The exact scenario order is the corresponding `@pytest.mark.parametrize` list
at `tests/test_preview_savedlayouts_page.py:13-72`,
`tests/test_fleetsharing_hydration.py:53-120`,
`tests/test_preview_group_backward.py:397-417`, and
`tests/test_preview_labelmarkers_page.py:13-39`. Task 1 materializes every full
label/program/protocol row and rejects any mismatch with the approved spec's
Frozen target inventory; this is stronger than maintaining a second hand-typed
list in the plan.

Direct one-shot argv remains:

```text
preview_savedlayouts.cjs DATA WEB_ROOT
preview_capture_sessions.cjs DATA WEB_ROOT
preview_dev_capture.cjs DATA WEB_ROOT
fleetsharing_page.cjs DATA SCENARIO WEB_ROOT
preview_group_backward.cjs DATA WEB_ROOT
preview_labelmarkers.cjs DATA WEB_ROOT
```

### Exact added IDs

```text
tests/test_node_scenario_worker.py::test_reply_numeric_schema_rejects_bool_id_and_nonfinite_or_negative_duration
tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[saved-layouts]
tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[fleet-sharing]
tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[group-backward]
tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[label-markers]
tests/test_persistent_page_workers.py::test_request_cleanup_after_success
tests/test_persistent_page_workers.py::test_request_cleanup_after_business_failure
tests/test_persistent_page_workers.py::test_saved_layout_receipt_is_durable_and_detached
```

The existing helper IDs remain exactly:

```text
tests/test_node_scenario_worker.py::test_real_node_worker_reuses_utf8_process_then_recovers_from_failure_timeout_and_crash
tests/test_node_scenario_worker.py::test_immediate_request_after_ok_reports_late_eof_context_and_recovers
tests/test_node_scenario_worker.py::test_broken_write_after_ok_reaps_status_and_prior_context
tests/test_node_scenario_worker.py::test_close_reports_exit_after_last_ok_reply_and_worker_remains_recoverable
tests/test_node_scenario_worker.py::test_failure_renders_javascript_stack_in_pytest_diagnostics
tests/test_node_scenario_worker.py::test_reply_ids_cannot_cross_requests_or_poison_the_next_restart
tests/test_node_scenario_worker.py::test_invalid_reply_schema_discards_process_with_context_and_restarts[not-object]
tests/test_node_scenario_worker.py::test_invalid_reply_schema_discards_process_with_context_and_restarts[missing-fields]
tests/test_node_scenario_worker.py::test_invalid_reply_schema_discards_process_with_context_and_restarts[wrong-ok-type]
tests/test_node_scenario_worker.py::test_invalid_reply_schema_discards_process_with_context_and_restarts[wrong-duration-type]
tests/test_node_scenario_worker.py::test_startup_failure_names_the_calling_scenario
tests/test_node_scenario_worker.py::test_malformed_reply_crashes_the_worker_and_the_next_request_restarts_cleanly
```

### Page manifest and request interfaces

Every module writes one UTF-8 JSON manifest with `allow_nan=False`:

```json
{"version":1,"pages":{"text":{"tag":"document","attrs":{},"children":[]},"structural":{"tag":"document","attrs":{},"children":[]}}}
```

Allowed page keys are exact by family: saved layouts `text,structural`; Fleet
Sharing `sharing`; group backward `structural`; label markers `structural`.
The worker command is exact:

```text
node tests/fixtures/page_scenario_worker.cjs --worker FAMILY WEB_ROOT MANIFEST_PATH
```

The Python request envelope remains owned by `NodeScenarioWorker`:

```python
reply = worker.request(
    "preview-saved-layouts/page/reversed",
    {"protocol": "saved-main", "input": input_payload},
    timeout=25.0,
)
```

The worker validates exactly the keys `id,scenario,payload`; positive safe integer
ID; nonempty family-valid label; exactly `protocol,input`; adapter-label match;
and a finite JSON input object. It reserializes input with the captured host JSON
serializer and parses it afresh in the request realm.

### Authoritative JUnit property contract

| Owner | Key | Exact value rule |
|---|---|---|
| Every one of 165 Node rows | `stage_b.worker_family` | one of `saved-layouts`, `fleet-sharing`, `group-backward`, `label-markers` from the frozen mapping |
| Every one of 165 Node rows | `stage_b.worker_pid` | positive decimal PID; exactly one PID per family in a healthy run |
| Every one of 165 Node rows | `stage_b.worker_request` | decimal family request ordinal; family sets exactly `1..62`, `1..65`, `1..17`, `1..21` |
| Every one of 205 existing target rows | `stage_b.direct_fsync_calls` | nonnegative decimal direct count; sums are 14 for Node rows and 43 for all existing rows |
| Only saved main `reversed` | `stage_b.receipt_build` | `saved-layout-main-v1` |
| Only saved main `reversed` | `stage_b.receipt_fsync_calls` | `19` |
| Every one of seven qualification IDs | `stage_b.qualification.worker_starts` | realm rows `1`; cleanup-success `1`; cleanup-failure exactly `3` (missing-input fatal, late-exit process, recovery process); receipt `0`; independent fatal-variant probe starts are separate overhead |
| Every one of seven qualification IDs | `stage_b.qualification.fsync_calls` | realm rows `0`; cleanup-success `4`; cleanup-failure `0`; receipt `0`; the separately owned shared receipt remains `19` |

If direct-input setup proves a different qualification-only fsync decomposition,
stop and update the spec before changing these frozen property values. Do not
fold the qualification `4` into 33 or 62.

---

### Task 1: Freeze the Merged PR #291 Baseline and Evidence Inputs

**Files:**
- Create: `docs/ci-persistent-page-workers-stage-b-results.md`
- Read: `/mnt/c/dev/flygd-wingman/tmp/stage-a-hosted-36258907685/**`
- Materialize outside the repository: `/tmp/stage-b-baseline/collect.py`, `ids.sh`, `test_ids.sh`, `test_collect.py`, `probe_plugin.py`, `hosted.py`, `restore.py`, `test_restore.py`, `mutations.py`, `test_mutations.py`, `verify_task2_identities.py`, structured collection JSON, ID-only `.ids.txt`, map/shape JSON, one-shot NDJSON, fsync JSON, JUnit XML, and hash manifests

**Interfaces:**
- Consumes: merged base `203d2068787cb3457916db6005afda0a7ce7a43a`, approved spec, current source, and accepted Stage A run `36258907685` attempt `1`.
- Produces: immutable baseline files for later identity, signature, output, launch, fsync, provenance, artifact, and scope comparisons.

- [ ] **Step 1: Verify the exact branch/base and clean starting tree**

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-persistent-page-workers-stage-b
git status --short --branch
git log -5 --oneline --decorate
test "$(git merge-base origin/main HEAD)" = 203d2068787cb3457916db6005afda0a7ce7a43a
test "$(git rev-parse origin/main)" = 203d2068787cb3457916db6005afda0a7ce7a43a
git diff --check
git diff --name-only origin/main...HEAD
```

Expected before Task 1 implementation: only the approved Stage B spec and plan
occur in the range; no executable path is dirty.

- [ ] **Step 2: Materialize only the collection/map/signature and raw-JUnit parser**

Start from a new `/tmp/stage-b-baseline` directory. Create
`/tmp/stage-b-baseline/collect.py`, `ids.sh`, `test_ids.sh`, and
`test_collect.py` first, with
these core checks; store complete records rather than terminal-only counts. This
step also materializes the longest-existing-module-prefix raw-JUnit parser used by
Step 3. It does **not** create, import, or run `restore.py`, `mutations.py`, or
either tooling test suite; those are ordered after the exact 217 baseline is
collected and bound.

```python
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

TARGET_FILES = (
    "tests/test_preview_savedlayouts_page.py",
    "tests/test_fleetsharing_hydration.py",
    "tests/test_preview_group_backward.py",
    "tests/test_preview_labelmarkers_page.py",
)
NODE_FUNCTIONS = {
    "tests/test_preview_savedlayouts_page.py": {
        "test_saved_layout_page_ordering": ("saved-layouts", "preview_savedlayouts.cjs", "saved-main"),
        "test_displayed_owner_controls_use_real_api_receipts": ("saved-layouts", "preview_savedlayouts.cjs", "saved-owner"),
        "test_capture_session_page_ordering": ("saved-layouts", None, None),
    },
    "tests/test_fleetsharing_hydration.py": {
        "test_sharing_watch_runtime": ("fleet-sharing", "fleetsharing_page.cjs", "fleet-sharing"),
    },
    "tests/test_preview_group_backward.py": {
        "test_group_backward_page": ("group-backward", "preview_group_backward.cjs", "group-backward"),
    },
    "tests/test_preview_labelmarkers_page.py": {
        "test_marker_page_ownership": ("label-markers", "preview_labelmarkers.cjs", "label-markers"),
    },
}


def ordered_id_file_hash(path: Path) -> str:
    data = path.read_bytes()
    validate_id_bytes(data)
    return hashlib.sha256(data).hexdigest()


def shape(path: Path) -> dict[str, object]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    result = {}
    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        result[node.name] = {
            "args": [arg.arg for arg in node.args.args],
            "posonlyargs": [arg.arg for arg in node.args.posonlyargs],
            "kwonlyargs": [arg.arg for arg in node.args.kwonlyargs],
            "vararg": None if node.args.vararg is None else node.args.vararg.arg,
            "kwarg": None if node.args.kwarg is None else node.args.kwarg.arg,
            "decorators": [ast.dump(item, include_attributes=False) for item in node.decorator_list],
        }
    return result
```

The following restoration interface is the contract for Step 4, not an action
in this step. Only after Step 3 has written and rebound the exact 217 IDs may
Step 4 create `/tmp/stage-b-baseline/restore.py`; no later task may invent or
patch a runner. It owns these frozen interfaces:

```python
from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from types import TracebackType
from typing import Literal

Phase = Literal["task3", "task4", "task5"]
ProbeKind = Literal["pytest", "external", "synthetic"]
EditRoot = Literal["worktree", "scratch"]


@dataclass(frozen=True)
class LiteralEdit:
    path: Path
    old: bytes
    new: bytes


@dataclass(frozen=True)
class PytestProbe:
    kind: Literal["pytest"]
    argv: tuple[str, ...]
    restored_argv: tuple[str, ...]


@dataclass(frozen=True)
class ExternalInvocation:
    argv: tuple[str, ...]
    exit_code: int
    stdout: bytes
    stderr: bytes
    sentinel_stream: Literal["stdout", "stderr"] | None


@dataclass(frozen=True)
class ExternalProbe:
    kind: Literal["external"]
    mutated: ExternalInvocation
    restored: ExternalInvocation


@dataclass(frozen=True)
class SyntheticInvocation:
    callable_name: str
    result_json: str | None
    exception_type: str | None
    exception_message: str | None


@dataclass(frozen=True)
class SyntheticProbe:
    kind: Literal["synthetic"]
    mutated: SyntheticInvocation
    restored: SyntheticInvocation


MutationProbe = PytestProbe | ExternalProbe | SyntheticProbe


@dataclass(frozen=True)
class MutationRecipe:
    name: str
    phase: Phase
    edit_root: EditRoot
    pytest_ids: tuple[str, ...]
    probe_label: str | None
    sentinel: str
    failure_regex: str
    forbidden_masking: tuple[str, ...]
    edits: tuple[LiteralEdit, ...]
    probe: MutationProbe


def git_bytes(worktree: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(worktree), *args])


def validate_recipe(recipe: MutationRecipe, edit_root: Path) -> None:
    assert recipe.name
    assert recipe.phase in ("task3", "task4", "task5")
    assert recipe.edit_root in ("worktree", "scratch")
    if recipe.probe.kind == "pytest":
        assert recipe.pytest_ids
        assert recipe.probe_label is None
    else:
        assert not recipe.pytest_ids
        assert recipe.probe_label is not None
    assert recipe.sentinel
    compiled = re.compile(recipe.failure_regex)
    assert recipe.failure_regex.startswith(r"\A")
    assert recipe.failure_regex.endswith(r"\Z")
    assert compiled.fullmatch(recipe.sentinel)
    assert recipe.forbidden_masking == FORBIDDEN_MASKING_BY_KIND[recipe.probe.kind]
    if recipe.probe.kind == "pytest":
        assert recipe.probe.argv and recipe.probe.restored_argv
    elif recipe.probe.kind == "external":
        assert recipe.probe.mutated.argv and recipe.probe.restored.argv
        assert recipe.probe.mutated.sentinel_stream in ("stdout", "stderr")
        assert recipe.probe.restored.sentinel_stream is None
    else:
        assert recipe.probe.kind == "synthetic"
        assert recipe.probe.mutated.callable_name
        assert recipe.probe.restored.callable_name
        assert exactly_one_synthetic_outcome(recipe.probe.mutated)
        assert exactly_one_synthetic_outcome(recipe.probe.restored)
    assert recipe.edits
    for path in {edit.path for edit in recipe.edits}:
        assert not path.is_absolute(), f"{recipe.name}: path was absolute"
        source = (edit_root / path).read_bytes()
        spans = []
        for edit in (item for item in recipe.edits if item.path == path):
            assert edit.old, f"{recipe.name}: empty old literal"
            assert edit.new, f"{recipe.name}: empty new literal"
            assert edit.old != edit.new, f"{recipe.name}: unchanged recipe"
            assert source.count(edit.old) == 1, (
                f"{recipe.name}: old literal cardinality was {source.count(edit.old)}"
            )
            start = source.index(edit.old)
            spans.append((start, start + len(edit.old)))
        ordered = sorted(spans)
        assert all(left[1] <= right[0] for left, right in pairwise(ordered)), (
            f"{recipe.name}: overlapping edits in {path}"
        )


def apply_literal_edits(original: bytes, edits: tuple[LiteralEdit, ...]) -> bytes:
    replacements = sorted(
        (
            original.index(edit.old),
            original.index(edit.old) + len(edit.old),
            edit.new,
        )
        for edit in edits
    )
    mutated = original
    for start, end, replacement in reversed(replacements):
        mutated = mutated[:start] + replacement + mutated[end:]
    return mutated


def mutate_once(
    edit_root: Path,
    recipe: MutationRecipe,
    probe: Callable[[], None],
) -> None:
    validate_recipe(recipe, edit_root)
    originals = {
        edit.path: (edit_root / edit.path).read_bytes() for edit in recipe.edits
    }
    original_hashes = {
        path: hashlib.sha256(content).hexdigest() for path, content in originals.items()
    }
    before_diff = git_bytes(edit_root, "diff", "--binary", "HEAD", "--", ".")
    before_status = git_bytes(
        edit_root, "status", "--porcelain=v2", "--untracked-files=all", "-z"
    )
    probe_error: BaseException | None = None
    probe_tb: TracebackType | None = None
    restore_error: BaseException | None = None
    try:
        for relative, original in originals.items():
            path = edit_root / relative
            edits = tuple(edit for edit in recipe.edits if edit.path == relative)
            mutated = apply_literal_edits(original, edits)
            assert mutated != original, f"{recipe.name}: mutation changed no bytes"
            path.write_bytes(mutated)
            assert path.read_bytes() == mutated
        probe()
    except BaseException as error:  # noqa: BLE001 -- restore before rethrow.
        probe_error = error
        probe_tb = error.__traceback__
    finally:
        try:
            for relative, original in originals.items():
                (edit_root / relative).write_bytes(original)
            checks = {
                "file bytes": all(
                    (edit_root / path).read_bytes() == original
                    for path, original in originals.items()
                ),
                "SHA-256": all(
                    hashlib.sha256((edit_root / path).read_bytes()).hexdigest()
                    == original_hashes[path]
                    for path in originals
                ),
                "binary diff": git_bytes(
                    edit_root, "diff", "--binary", "HEAD", "--", "."
                )
                == before_diff,
                "porcelain status": git_bytes(
                    edit_root,
                    "status",
                    "--porcelain=v2",
                    "--untracked-files=all",
                    "-z",
                )
                == before_status,
            }
            mismatches = [name for name, matched in checks.items() if not matched]
            if mismatches:
                mismatch = AssertionError("restoration bytes mismatch")
                mismatch.add_note(", ".join(mismatches))
                raise mismatch
        except BaseException as error:  # noqa: BLE001 -- restoration wins.
            restore_error = AssertionError("restoration bytes mismatch")
            restore_error.add_note(str(error))
    if restore_error is not None:
        raise restore_error from probe_error
    if probe_error is not None:
        raise probe_error.with_traceback(probe_tb)
```

On top of that exact restoration primitive, `restore.py` must contain one
strict dispatcher with three non-interchangeable probe paths:

- `run_pytest_probe()` runs the exact registered pytest command in a fresh
  process and parses only its raw JUnit. It requires the exact registered
  testcase IDs, nonzero mutated exit, exactly one intended call-phase
  `<failure>`, no setup/teardown `<error>` or `<skipped>`, traceback presence,
  and exactly one extracted assertion-message line that full-matches the
  recipe regex. Its restored command requires every registered restored ID to
  pass exactly once. It never treats terminal prose as an outcome.
- `run_external_probe()` runs the exact registered command without pytest or
  JUnit interpretation. It requires the registered exit code and byte-exact
  stdout and stderr for both mutated and restored invocations, requires the
  sentinel in exactly the registered stream for the mutated invocation, and
  rejects it from the other stream and restored outputs.
- `run_synthetic_probe()` looks up the exact registered callable name in a
  closed `SYNTHETIC_PROBES` map and invokes it in-process. It compares the
  registered JSON result byte-for-byte or requires the registered exception
  class and exact message; exactly one of result or exception is legal for
  each mutated/restored invocation. It creates no JUnit and accepts no command.

`run_recipe()` validates literal old/new bytes before mutation, proves mutated
bytes differ, dispatches strictly on `recipe.probe.kind`, applies the
kind-specific masking rules, restores exact bytes/SHA-256/binary diff/NUL-
delimited porcelain in `finally`, and only then dispatches the matching restored
probe. A failure to restore any surface raises exact `restoration bytes
mismatch`. Pytest-only rules such as testcase phase and JUnit traceback are
never applied to `external` or `synthetic` probes; `external::...` and
`synthetic::...` values are registry labels, never pytest node IDs. All three
kinds share at least one literal match-once edit, rejection of every other
registered sentinel, kind-appropriate forbidden masking, and exact restoration.
Every recipe declares `edit_root`. `worktree` means the Stage B worktree;
`scratch` means a freshly initialized disposable Git repository containing the
canonical external/synthetic fixture bytes. The runner snapshots and restores
the selected root identically, so an in-process probe cannot bypass literal edit
or restoration evidence merely because it creates no JUnit.

Literal edits are Python `bytes`, not line numbers, ellipses, pseudocode,
search-only descriptions, or regex substitutions.

#### Baseline and planned pytest identity domains

Task 1's structured baseline collection report is converted through
`ids-from-collection`; the resulting `baseline-217.ids.txt` defines
`BASELINE_COLLECTED_IDS` as the exact 205 target IDs followed by the exact 12
existing helper IDs—217 unique IDs, with the
frozen constituent hashes and order already required above. Future IDs are not
looked up in current pytest collection. They are declared separately and exactly
from the approved spec:

```python
APPROVED_PLANNED_ID_ROWS = (
    (
        "tests/test_node_scenario_worker.py::test_reply_numeric_schema_rejects_bool_id_and_nonfinite_or_negative_duration",
        "tests/test_node_scenario_worker.py",
        "test_reply_numeric_schema_rejects_bool_id_and_nonfinite_or_negative_duration",
        None,
        "task2",
    ),
    (
        "tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[saved-layouts]",
        "tests/test_persistent_page_workers.py",
        "test_request_realm_is_fresh_and_program_is_reexecuted",
        "saved-layouts",
        "task2",
    ),
    (
        "tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[fleet-sharing]",
        "tests/test_persistent_page_workers.py",
        "test_request_realm_is_fresh_and_program_is_reexecuted",
        "fleet-sharing",
        "task2",
    ),
    (
        "tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[group-backward]",
        "tests/test_persistent_page_workers.py",
        "test_request_realm_is_fresh_and_program_is_reexecuted",
        "group-backward",
        "task2",
    ),
    (
        "tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[label-markers]",
        "tests/test_persistent_page_workers.py",
        "test_request_realm_is_fresh_and_program_is_reexecuted",
        "label-markers",
        "task2",
    ),
    (
        "tests/test_persistent_page_workers.py::test_request_cleanup_after_success",
        "tests/test_persistent_page_workers.py",
        "test_request_cleanup_after_success",
        None,
        "task2",
    ),
    (
        "tests/test_persistent_page_workers.py::test_request_cleanup_after_business_failure",
        "tests/test_persistent_page_workers.py",
        "test_request_cleanup_after_business_failure",
        None,
        "task2",
    ),
    (
        "tests/test_persistent_page_workers.py::test_saved_layout_receipt_is_durable_and_detached",
        "tests/test_persistent_page_workers.py",
        "test_saved_layout_receipt_is_durable_and_detached",
        None,
        "task2",
    ),
)
APPROVED_PLANNED_IDS = frozenset(row[0] for row in APPROVED_PLANNED_ID_ROWS)
APPROVED_PLANNED_OWNERS = {
    nodeid: (module, function, parameter, task)
    for nodeid, module, function, parameter, task in APPROVED_PLANNED_ID_ROWS
}
assert len(APPROVED_PLANNED_ID_ROWS) == 8
assert len(APPROVED_PLANNED_IDS) == 8
assert set(APPROVED_PLANNED_OWNERS) == set(APPROVED_PLANNED_IDS)
assert APPROVED_PLANNED_IDS == ids_parsed_from_approved_spec
assert not (BASELINE_COLLECTED_IDS & APPROVED_PLANNED_IDS)
```

`validate_identity_domains()` parses every declared pytest ID with exact grammar
`tests/<module>.py::test_<function>` plus at most one nonempty bracketed
parameter, then requires the parsed module/function/parameter tuple and creation
phase to equal `APPROVED_PLANNED_OWNERS`. It receives only selected IDs from
recipes whose probe kind is `pytest`; non-pytest labels are validated separately
against the exact external/synthetic allowlist. For every selected pytest ID it
accepts exactly one of two states:

1. the ID is in `BASELINE_COLLECTED_IDS`; or
2. the ID is absent from baseline, is in `APPROVED_PLANNED_IDS`, and has its
   exact declared Task 2 owner tuple.

The set of non-baseline selected pytest IDs across all 71 recipes must equal
`APPROVED_PLANNED_IDS`—not merely be a subset. The executable check is:

```python
PLANNED_NODEID = re.compile(
    r"\A(?P<module>tests(?:/[A-Za-z0-9_]+)+\.py)::"
    r"(?P<function>test_[A-Za-z0-9_]+)"
    r"(?:\[(?P<parameter>[^\[\]\r\n]+)\])?\Z"
)


def validate_identity_domains(
    baseline_ids: frozenset[str],
    planned_rows: tuple[tuple[str, str, str, str | None, str], ...],
    selected_pytest_ids: frozenset[str],
) -> None:
    planned_ids = tuple(row[0] for row in planned_rows)
    assert len(baseline_ids) == 217
    assert len(planned_ids) == 8
    assert len(set(planned_ids)) == 8
    assert set(planned_ids) == set(APPROVED_PLANNED_IDS)
    assert set(planned_ids).isdisjoint(baseline_ids)
    for nodeid, module, function, parameter, task in planned_rows:
        parsed = PLANNED_NODEID.fullmatch(nodeid)
        assert parsed is not None
        assert parsed.group("module") == module
        assert parsed.group("function") == function
        assert parsed.group("parameter") == parameter
        assert task == "task2"
        assert APPROVED_PLANNED_OWNERS[nodeid] == (
            module,
            function,
            parameter,
            task,
        )
    undeclared = selected_pytest_ids - baseline_ids - APPROVED_PLANNED_IDS
    assert not undeclared
    assert selected_pytest_ids - baseline_ids == APPROVED_PLANNED_IDS
```

Thus a typo future ID, an undeclared missing ID, a duplicate planned row, a wrong
module/function/parameter owner, or a future ID unexpectedly present in the 217
baseline fails Task 1, while a correctly declared future ID does not require
collection before its file exists. After binding the actual 217 IDs, Task 1
materializes `verify_task2_identities.py` from these same constants. It writes
`expected-task2-relevant-225.collection.json` by inserting the helper-contract
record immediately after the existing `wrong-duration-type` helper row and
appending the seven qualification records in their declared source order after
the 205 target plus 13-helper sequence. It writes
`expected-task2-complete-16617.collection.json` from the accepted exact 16,609
order by inserting the helper record at that same module-local anchor and
inserting the new `tests/test_persistent_page_workers.py` records at that file's
exact lexical collection position, between the existing `paths_engine` and
`poll_tick` modules. It then invokes `ids-from-collection` separately for each to
produce `expected-task2-relevant-225.ids.txt` and
`expected-task2-complete-16617.ids.txt`. Both ID files have one final newline and
frozen SHA-256 values. Self-tests cover the five owner/domain rejections plus wrong
insertion anchor/order; the real 225/16,617 collections do not exist until Task
2 and are not claimed here.

#### One canonical mutation registry

After the 217 baseline is bound, Task 1 Step 4 creates
`/tmp/stage-b-baseline/mutations.py` and `test_mutations.py`. `mutations.py` is
the only mutation authority for the rest of the plan. Each of its exactly **71**
`MutationRecipe` objects contains its literal name, earliest execution phase,
typed `pytest`/`external`/`synthetic` probe, exact selected pytest node IDs or
exact non-pytest labels, literal sentinel, anchored regex, kind-appropriate
forbidden masking rules, match-once byte edits, and complete mutated/restored
expectations. No Task 3/4/5 prose table may restate an owner, sentinel, regex,
edit, or probe. Those tasks invoke only the phase tuples below by recipe name.

The registry declares exact node-ID constants rather than aliases such as
"saved realm row":

```python
NUMERIC_ID = "tests/test_node_scenario_worker.py::test_reply_numeric_schema_rejects_bool_id_and_nonfinite_or_negative_duration"
MISSING_FIELDS_ID = "tests/test_node_scenario_worker.py::test_invalid_reply_schema_discards_process_with_context_and_restarts[missing-fields]"
REALM_SAVED_ID = "tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[saved-layouts]"
REALM_SHARING_ID = "tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[fleet-sharing]"
REALM_GROUP_ID = "tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[group-backward]"
REALM_MARKER_ID = "tests/test_persistent_page_workers.py::test_request_realm_is_fresh_and_program_is_reexecuted[label-markers]"
CLEANUP_SUCCESS_ID = "tests/test_persistent_page_workers.py::test_request_cleanup_after_success"
CLEANUP_FAILURE_ID = "tests/test_persistent_page_workers.py::test_request_cleanup_after_business_failure"
RECEIPT_ID = "tests/test_persistent_page_workers.py::test_saved_layout_receipt_is_durable_and_detached"
SAVED_REVERSED_ID = "tests/test_preview_savedlayouts_page.py::test_saved_layout_page_ordering[reversed]"
SHARING_REJECT_ID = "tests/test_fleetsharing_hydration.py::test_sharing_watch_runtime[reject]"
SHARING_SOURCE_REJECTION_ID = "tests/test_fleetsharing_hydration.py::test_sharing_watch_runtime[bridge-source-rejection]"
GROUP_DIALOG_OWNERS_ID = "tests/test_preview_group_backward.py::test_group_backward_page[focus-dialog-owners]"
GROUP_OWN_DIALOG_ID = "tests/test_preview_group_backward.py::test_group_backward_page[focus-own-dialog]"
MARKER_DEFERRED_ID = "tests/test_preview_labelmarkers_page.py::test_marker_page_ownership[screenshot-deferred]"

RESTORED_ONLY_IDS = frozenset({
    "tests/test_node_scenario_worker.py::test_immediate_request_after_ok_reports_late_eof_context_and_recovers",
    "tests/test_node_scenario_worker.py::test_broken_write_after_ok_reaps_status_and_prior_context",
    "tests/test_node_scenario_worker.py::test_close_reports_exit_after_last_ok_reply_and_worker_remains_recoverable",
})
RESTORED_ONLY_BY_RECIPE = {
    "late-rejection-attribution": (
        "tests/test_node_scenario_worker.py::test_immediate_request_after_ok_reports_late_eof_context_and_recovers",
        "tests/test_node_scenario_worker.py::test_broken_write_after_ok_reaps_status_and_prior_context",
        "tests/test_node_scenario_worker.py::test_close_reports_exit_after_last_ok_reply_and_worker_remains_recoverable",
    ),
}
```

These three helper IDs are not selected failure owners and are not members of
`EXPECTED_OWNERS["late-rejection-attribution"]`. They run only after the
recipe's bytes/hash/diff/status restoration has succeeded; each must produce one
passed JUnit testcase with no failure/error/skip. The registry runner never
feeds them to the mutated side of `run_pytest_probe()` and never searches them
for the mutation sentinel.

Non-pytest selected values are labels, never pytest IDs. External-process labels
are the exact strings under `external::fatal/*`,
`external::inventory/node-165`, and
`external::saved-main/receipt-count-55`. In-process labels are exactly
`synthetic::junit/property-cardinality` and
`synthetic::runner/restoration`. Registry construction fails for any other
non-pytest label or for a label whose prefix does not agree with its probe kind.
The owner map is literal rather than inferred from a prefix:

```python
NONPYTEST_LABELS_BY_RECIPE = {
    "receipt-once-construction": ("external::saved-main/receipt-count-55",),
    "protocol-malformed-ndjson": ("external::fatal/malformed-ndjson",),
    "protocol-wrong-family": ("external::fatal/wrong-family",),
    "protocol-unknown-protocol": ("external::fatal/unknown-protocol",),
    "protocol-unknown-scenario": ("external::fatal/unknown-scenario",),
    "inventory-node-165": ("external::inventory/node-165",),
    "junit-property-cardinality": ("synthetic::junit/property-cardinality",),
    "restoration-byte-integrity": ("synthetic::runner/restoration",),
}
NONPYTEST_KIND_BY_LABEL = {
    "external::saved-main/receipt-count-55": "external",
    "external::fatal/malformed-ndjson": "external",
    "external::fatal/wrong-family": "external",
    "external::fatal/unknown-protocol": "external",
    "external::fatal/unknown-scenario": "external",
    "external::inventory/node-165": "external",
    "synthetic::junit/property-cardinality": "synthetic",
    "synthetic::runner/restoration": "synthetic",
}
assert len(NONPYTEST_KIND_BY_LABEL) == 8
```

The exact phase contract is:

```python
ALLOWED_PHASES_BY_ID = {
    NUMERIC_ID: frozenset({"task5"}),
    MISSING_FIELDS_ID: frozenset({"task5"}),
    REALM_SAVED_ID: frozenset({"task3", "task4", "task5"}),
    REALM_SHARING_ID: frozenset({"task4", "task5"}),
    REALM_GROUP_ID: frozenset({"task4", "task5"}),
    REALM_MARKER_ID: frozenset({"task4", "task5"}),
    CLEANUP_SUCCESS_ID: frozenset({"task5"}),
    CLEANUP_FAILURE_ID: frozenset({"task4", "task5"}),
    RECEIPT_ID: frozenset({"task3"}),
    SAVED_REVERSED_ID: frozenset({"task3"}),
    SHARING_REJECT_ID: frozenset({"task4"}),
    SHARING_SOURCE_REJECTION_ID: frozenset({"task4"}),
    GROUP_DIALOG_OWNERS_ID: frozenset({"task4"}),
    GROUP_OWN_DIALOG_ID: frozenset({"task4"}),
    MARKER_DEFERRED_ID: frozenset({"task4"}),
    "external::fatal/malformed-ndjson": frozenset({"task4"}),
    "external::fatal/wrong-family": frozenset({"task4"}),
    "external::fatal/unknown-protocol": frozenset({"task4"}),
    "external::fatal/unknown-scenario": frozenset({"task4"}),
    "external::inventory/node-165": frozenset({"task4"}),
    "external::saved-main/receipt-count-55": frozenset({"task3"}),
    "synthetic::junit/property-cardinality": frozenset({"task5"}),
    "synthetic::runner/restoration": frozenset({"task5"}),
}
```

`test_mutations.py` checks every recipe's selected value against this map. A
pytest restored argv may include an additional anti-mask ID from the map, but a
pytest recipe's `pytest_ids` contains only testcases expected in its mutated
JUnit result. External and synthetic recipes instead carry one exact
`probe_label` and never pass that label to pytest.

The selected failure owner is defined only by the exhaustive
`EXPECTED_OWNERS` map below; no recipe stores an owner nickname or relies
on prefix inference.

The three phase tuples partition the registry—each recipe name occurs here
exactly once:

```python
TASK3_RECIPES = (
    "realm-saved-context-reuse",
    "realm-saved-source-reexecution",
    "realm-saved-input-detachment",
    "realm-saved-prior-reply-detachment",
    "realm-saved-module-export-isolation",
    "realm-saved-promise-completion",
    "receipt-pending-first-apply",
    "receipt-production-identity",
    "receipt-durable-readback",
    "receipt-atomic-writer-fsync",
    "receipt-writer-restoration",
    "receipt-environment-restoration",
    "receipt-reader-release",
    "receipt-once-construction",
)

TASK4_RECIPES = (
    "adapter-saved-program-selection",
    "adapter-sharing-dom-isolation",
    "realm-group-source-reexecution",
    "adapter-marker-root-release",
    "business-failure-process-retention",
    "protocol-fatal-no-replay",
    "protocol-malformed-ndjson",
    "protocol-wrong-family",
    "protocol-unknown-protocol",
    "protocol-unknown-scenario",
    "diagnostics-sharing-reject",
    "diagnostics-sharing-source-order",
    "group-dialog-owner-matrix",
    "group-own-dialog-matrix",
    "marker-deferred-roster",
    "inventory-node-165",
)

TASK5_RECIPES = (
    "schema-bool-id-rejected",
    "schema-bool-id-terminated",
    "schema-bool-id-discarded",
    "schema-bool-id-new-pid",
    "schema-bool-duration-rejected",
    "schema-bool-duration-discarded",
    "schema-negative-duration-rejected",
    "schema-nan-duration-rejected",
    "schema-positive-infinity-rejected",
    "schema-negative-infinity-rejected",
    "schema-zero-duration-accepted",
    "schema-float-duration-accepted",
    "schema-missing-fields-protocol-error",
    "schema-missing-fields-discarded",
    "realm-saved-host-isolation",
    "realm-sharing-host-isolation",
    "realm-group-host-isolation",
    "realm-marker-host-isolation",
    "source-target-not-host-required",
    "realm-sharing-module-export-isolation",
    "realm-group-module-export-isolation",
    "realm-marker-module-export-isolation",
    "realm-sharing-context-reuse",
    "realm-group-context-reuse",
    "realm-marker-context-reuse",
    "realm-sharing-source-reexecution",
    "realm-marker-source-reexecution",
    "realm-saved-pristine-intrinsics",
    "failure-hostile-error-detachment",
    "failure-primitive-detachment",
    "cleanup-timer-cancellation",
    "cleanup-listener-release",
    "cleanup-unresolved-promise-release",
    "rejection-before-settlement",
    "rejection-boundary-turn",
    "rejection-raw-reference-release",
    "cleanup-before-reply",
    "protocol-fatal-no-reply",
    "late-rejection-attribution",
    "junit-property-cardinality",
    "restoration-byte-integrity",
)

assert len(TASK3_RECIPES) == 14
assert len(TASK4_RECIPES) == 16
assert len(TASK5_RECIPES) == 41
assert len(TASK3_RECIPES + TASK4_RECIPES + TASK5_RECIPES) == 71

EXPECTED_OWNERS = {
    "realm-saved-context-reuse": (REALM_SAVED_ID,),
    "realm-saved-source-reexecution": (REALM_SAVED_ID,),
    "realm-saved-input-detachment": (REALM_SAVED_ID,),
    "realm-saved-prior-reply-detachment": (REALM_SAVED_ID,),
    "realm-saved-module-export-isolation": (REALM_SAVED_ID,),
    "realm-saved-promise-completion": (REALM_SAVED_ID,),
    "receipt-pending-first-apply": (RECEIPT_ID,),
    "receipt-production-identity": (RECEIPT_ID,),
    "receipt-durable-readback": (RECEIPT_ID,),
    "receipt-atomic-writer-fsync": (RECEIPT_ID,),
    "receipt-writer-restoration": (RECEIPT_ID,),
    "receipt-environment-restoration": (RECEIPT_ID,),
    "receipt-reader-release": (RECEIPT_ID,),
    "receipt-once-construction": ("external::saved-main/receipt-count-55",),
    "adapter-saved-program-selection": (REALM_SAVED_ID,),
    "adapter-sharing-dom-isolation": (REALM_SHARING_ID,),
    "realm-group-source-reexecution": (REALM_GROUP_ID,),
    "adapter-marker-root-release": (REALM_MARKER_ID,),
    "business-failure-process-retention": (CLEANUP_FAILURE_ID,),
    "protocol-fatal-no-replay": (CLEANUP_FAILURE_ID,),
    "protocol-malformed-ndjson": ("external::fatal/malformed-ndjson",),
    "protocol-wrong-family": ("external::fatal/wrong-family",),
    "protocol-unknown-protocol": ("external::fatal/unknown-protocol",),
    "protocol-unknown-scenario": ("external::fatal/unknown-scenario",),
    "diagnostics-sharing-reject": (SHARING_REJECT_ID,),
    "diagnostics-sharing-source-order": (SHARING_SOURCE_REJECTION_ID,),
    "group-dialog-owner-matrix": (GROUP_DIALOG_OWNERS_ID,),
    "group-own-dialog-matrix": (GROUP_OWN_DIALOG_ID,),
    "marker-deferred-roster": (MARKER_DEFERRED_ID,),
    "inventory-node-165": ("external::inventory/node-165",),
    "schema-bool-id-rejected": (NUMERIC_ID,),
    "schema-bool-id-terminated": (NUMERIC_ID,),
    "schema-bool-id-discarded": (NUMERIC_ID,),
    "schema-bool-id-new-pid": (NUMERIC_ID,),
    "schema-bool-duration-rejected": (NUMERIC_ID,),
    "schema-bool-duration-discarded": (NUMERIC_ID,),
    "schema-negative-duration-rejected": (NUMERIC_ID,),
    "schema-nan-duration-rejected": (NUMERIC_ID,),
    "schema-positive-infinity-rejected": (NUMERIC_ID,),
    "schema-negative-infinity-rejected": (NUMERIC_ID,),
    "schema-zero-duration-accepted": (NUMERIC_ID,),
    "schema-float-duration-accepted": (NUMERIC_ID,),
    "schema-missing-fields-protocol-error": (MISSING_FIELDS_ID,),
    "schema-missing-fields-discarded": (MISSING_FIELDS_ID,),
    "realm-saved-host-isolation": (REALM_SAVED_ID,),
    "realm-sharing-host-isolation": (REALM_SHARING_ID,),
    "realm-group-host-isolation": (REALM_GROUP_ID,),
    "realm-marker-host-isolation": (REALM_MARKER_ID,),
    "source-target-not-host-required": (CLEANUP_SUCCESS_ID,),
    "realm-sharing-module-export-isolation": (REALM_SHARING_ID,),
    "realm-group-module-export-isolation": (REALM_GROUP_ID,),
    "realm-marker-module-export-isolation": (REALM_MARKER_ID,),
    "realm-sharing-context-reuse": (REALM_SHARING_ID,),
    "realm-group-context-reuse": (REALM_GROUP_ID,),
    "realm-marker-context-reuse": (REALM_MARKER_ID,),
    "realm-sharing-source-reexecution": (REALM_SHARING_ID,),
    "realm-marker-source-reexecution": (REALM_MARKER_ID,),
    "realm-saved-pristine-intrinsics": (REALM_SAVED_ID,),
    "failure-hostile-error-detachment": (CLEANUP_FAILURE_ID,),
    "failure-primitive-detachment": (CLEANUP_FAILURE_ID,),
    "cleanup-timer-cancellation": (CLEANUP_SUCCESS_ID,),
    "cleanup-listener-release": (CLEANUP_SUCCESS_ID,),
    "cleanup-unresolved-promise-release": (CLEANUP_SUCCESS_ID,),
    "rejection-before-settlement": (CLEANUP_FAILURE_ID,),
    "rejection-boundary-turn": (CLEANUP_FAILURE_ID,),
    "rejection-raw-reference-release": (CLEANUP_FAILURE_ID,),
    "cleanup-before-reply": (CLEANUP_SUCCESS_ID,),
    "protocol-fatal-no-reply": (CLEANUP_FAILURE_ID,),
    "late-rejection-attribution": (CLEANUP_FAILURE_ID,),
    "junit-property-cardinality": ("synthetic::junit/property-cardinality",),
    "restoration-byte-integrity": ("synthetic::runner/restoration",),
}
assert len(EXPECTED_OWNERS) == 71
assert set(EXPECTED_OWNERS) == set(
    TASK3_RECIPES + TASK4_RECIPES + TASK5_RECIPES
)

REPRESENTATIVE_EVIDENCE_RECIPES = (
    "schema-bool-id-terminated",
    "realm-saved-context-reuse",
    "protocol-malformed-ndjson",
    "receipt-pending-first-apply",
    "junit-property-cardinality",
    "restoration-byte-integrity",
)
assert set(REPRESENTATIVE_EVIDENCE_RECIPES) <= set(EXPECTED_OWNERS)
```

These six canonical recipes produce seven actual defect executions because
`junit-property-cardinality` owns two internal variants. They run at their own
registered phases—not during plan authoring—and are called out as the bounded
representative evidence subset after all seven mutated/restored results exist.

Every recipe stores its own literal sentinel and its separately spelled literal
anchored regex; neither is derived at probe time. For example, the canonical
property regex is `\Astage_b\ property\ cardinality\Z` and the restoration regex
is `\Arestoration\ bytes\ mismatch\Z`. All recipe sentinels are unique. The
single `junit-property-cardinality` recipe internally runs both
missing-property and duplicate-identical-property variants against its one
canonical sentinel/regex, exactly `stage_b property cardinality`; it is one
registry object and one phase reference, not two recipes. The other frozen
non-prefixed sentinels are the mode-qualified `numeric-schema ...` messages from
the helper—including exact `numeric-schema bool-id: rejected process was not
terminated`—and exact `restoration bytes mismatch`. Every remaining registry
entry stores the fully expanded literal `stage-b mutation ` followed by its
canonical name; angle-bracket or generated placeholders are forbidden. Owning
test/probe assertions use only that canonical text; no legacy sentinel alias is
retained.

The 14 schema entries preserve these exact helper messages as their sentinels:
`numeric-schema bool-id: invalid reply was accepted`, `numeric-schema bool-id:
rejected process was not terminated`, `numeric-schema bool-id: process was not
discarded`, `numeric-schema bool-id: recovery reused discarded PID`,
`numeric-schema bool-duration: invalid reply was accepted`, `numeric-schema
bool-duration: process was not discarded`, `numeric-schema negative: invalid
reply was accepted`, `numeric-schema nan: invalid reply was accepted`,
`numeric-schema positive-infinity: invalid reply was accepted`, `numeric-schema
negative-infinity: invalid reply was accepted`, `numeric-schema zero: valid
duration rejected`, `numeric-schema float: valid duration rejected`,
`missing-fields reply did not use _ProtocolError`, and `missing-fields process
was not discarded`. These literals occur only in `REGISTRY` and their owning
assertions; no shorter numeric regex is accepted.

Masking is exact and appropriate to probe kind:

```python
PYTEST_FORBIDDEN_MASKING = (
    r"\bImportError\b",
    r"\bModuleNotFoundError\b",
    r"\bNodeScenarioTimeout\b",
    r"\bDID NOT RAISE\b",
    r"fixture ['\"][^'\"]+['\"] not found",
    r"ERROR collecting",
    r"(?i:\btime(?:d)? out\b|\btimeout\b)",
)
EXTERNAL_FORBIDDEN_MASKING = (
    r"\bNodeScenarioTimeout\b",
    r"(?i:\btime(?:d)? out\b|\btimeout\b)",
)
SYNTHETIC_FORBIDDEN_MASKING = (
    r"\bImportError\b",
    r"\bModuleNotFoundError\b",
    r"(?i:\btime(?:d)? out\b|\btimeout\b)",
)
FORBIDDEN_MASKING_BY_KIND = {
    "pytest": PYTEST_FORBIDDEN_MASKING,
    "external": EXTERNAL_FORBIDDEN_MASKING,
    "synthetic": SYNTHETIC_FORBIDDEN_MASKING,
}
```

Every path also rejects any other recipe sentinel. The JUnit parser additionally
requires the intended call phase and rejects setup/teardown `<error>` elements;
those pytest-specific concepts are not imposed on process or in-process probes.
No generic failure or kind-appropriate masking event can satisfy a recipe.
`REGISTRY` is a literal dict in exact
`TASK3_RECIPES + TASK4_RECIPES + TASK5_RECIPES` insertion order; every value is a
fully spelled `MutationRecipe(...)` with a typed probe, not a factory output or
later override.

`validate_registry()` is the mandatory preflight:

```python
from collections import Counter


def validate_registry(
    worktree: Path,
    baseline_collected_ids: frozenset[str],
    phase: Phase | None = None,
    scratch_root: Path | None = None,
) -> None:
    references = TASK3_RECIPES + TASK4_RECIPES + TASK5_RECIPES
    assert len(references) == 71
    assert len(set(references)) == 71
    assert tuple(REGISTRY) == references
    assert all(name == recipe.name for name, recipe in REGISTRY.items())
    assert len({recipe.sentinel for recipe in REGISTRY.values()}) == 71
    assert {
        name for name, recipe in REGISTRY.items() if recipe.probe.kind != "pytest"
    } == set(NONPYTEST_LABELS_BY_RECIPE)
    assert {
        label for labels in NONPYTEST_LABELS_BY_RECIPE.values() for label in labels
    } == set(NONPYTEST_KIND_BY_LABEL)
    expected_probe_type = {
        "pytest": PytestProbe,
        "external": ExternalProbe,
        "synthetic": SyntheticProbe,
    }
    assert all(
        type(recipe.probe) is expected_probe_type[recipe.probe.kind]
        for recipe in REGISTRY.values()
    )
    pytest_selected_ids = frozenset(
        nodeid
        for recipe in REGISTRY.values()
        for nodeid in recipe.pytest_ids
    )
    validate_identity_domains(
        baseline_collected_ids,
        APPROVED_PLANNED_ID_ROWS,
        pytest_selected_ids,
    )
    declared_ids = baseline_collected_ids | APPROVED_PLANNED_IDS

    for recipe in REGISTRY.values():
        owners = recipe.pytest_ids or (recipe.probe_label,)
        assert owners == EXPECTED_OWNERS[recipe.name]
        assert recipe.phase in ALLOWED_PHASES_BY_ID[owners[0]]
        assert all(
            owner in ALLOWED_PHASES_BY_ID
            and recipe.phase in ALLOWED_PHASES_BY_ID[owner]
            for owner in owners
        )
        if recipe.probe.kind == "pytest":
            assert all(nodeid in declared_ids for nodeid in recipe.pytest_ids)
            assert all(nodeid.startswith("tests/") for nodeid in recipe.pytest_ids)
        else:
            assert (recipe.probe_label,) == NONPYTEST_LABELS_BY_RECIPE[recipe.name]
            assert NONPYTEST_KIND_BY_LABEL[recipe.probe_label] == recipe.probe.kind
        assert recipe.forbidden_masking == FORBIDDEN_MASKING_BY_KIND[recipe.probe.kind]
        assert re.fullmatch(recipe.failure_regex, recipe.sentinel)
        assert sum(
            bool(re.fullmatch(other.failure_regex, recipe.sentinel))
            for other in REGISTRY.values()
        ) == 1
        assert not any(
            re.search(mask, recipe.sentinel) or re.search(mask, recipe.failure_regex)
            for mask in recipe.forbidden_masking
        )

    restored_references = Counter(
        nodeid
        for nodeids in RESTORED_ONLY_BY_RECIPE.values()
        for nodeid in nodeids
    )
    assert set(RESTORED_ONLY_BY_RECIPE) == {"late-rejection-attribution"}
    assert set(restored_references) == set(RESTORED_ONLY_IDS)
    assert all(count == 1 for count in restored_references.values())
    assert all(nodeid in baseline_collected_ids for nodeid in RESTORED_ONLY_IDS)
    for recipe_name, nodeids in RESTORED_ONLY_BY_RECIPE.items():
        recipe = REGISTRY[recipe_name]
        assert set(nodeids).isdisjoint(recipe.pytest_ids)
        assert recipe.probe.kind == "pytest"
        mutated_argv = Counter(recipe.probe.argv)
        restored_argv = Counter(recipe.probe.restored_argv)
        assert all(mutated_argv[nodeid] == 0 for nodeid in nodeids)
        assert all(restored_argv[nodeid] == 1 for nodeid in nodeids)

    if phase is not None:
        expected = {
            "task3": TASK3_RECIPES,
            "task4": TASK4_RECIPES,
            "task5": TASK5_RECIPES,
        }[phase]
        selected = tuple(
            recipe
            for recipe in REGISTRY.values()
            if recipe.phase == phase
        )
        assert tuple(recipe.name for recipe in selected) == expected
        for recipe in selected:
            edit_root = worktree
            if recipe.edit_root == "scratch":
                assert scratch_root is not None
                edit_root = scratch_root
            validate_recipe(recipe, edit_root)
```

Task 1 calls `validate_registry(..., phase=None)` only: metadata, kind,
identity/label owner, phase, sentinel/regex, masking, and serialized-manifest
smoke. It does not call `validate_recipe()` on future implementation bytes and
does not report any real edit as qualified. A generic disposable fixture tests
runner restoration separately. The exact-phase `validate_registry()` call is
the first operation after that phase's GREEN implementation and requires every
real old literal to match once before any mutation. This does not permit changing
registry metadata after its Task 1 manifest hash is frozen.

`test_mutations.py` imports and validates the actual `REGISTRY` objects and
serialized manifest; it must not construct a shadow registry from the phase-name
lists or disposable placeholder edits. It must prove before Task 3:

1. registry keys, `recipe.name`, and the concatenated phase references are the
   same 71-name set, with every reference count exactly one;
2. all names and sentinels are unique, with the property variants contained
   inside their one canonical recipe;
3. every anchored regex full-matches its own sentinel, and no sentinel
   full-matches any other recipe's regex;
4. every recipe's typed `pytest_ids` or singleton `probe_label` equals its
   `EXPECTED_OWNERS` tuple exactly; every
   pytest ID exists in the frozen/planned identity domains, every external or
   synthetic label exists in its explicit kind/owner allowlist, and each permits
   that recipe's phase, with explicit assertions for the corrected receipt-count,
   two sharing-diagnostic, two group-matrix, and marker-deferred owners;
5. every recipe carries at least one literal edit with an exact edit root, its
   exact typed probe, and kind-specific masking tuple: pytest commands plus
   restored commands, external commands plus exact
   exit/stdout/stderr/sentinel stream, or synthetic callable plus exact
   result/exception; metadata smoke rejects generated `before:<name>`/`after:<name>`
   bytes, fake commands, no-op callables, and placeholder paths, but deliberately
   defers real-target match-once qualification to the owning GREEN phase;
6. no sentinel or regex contains a placeholder, generic timeout/setup/
   collection text, or `DID NOT RAISE`;
7. all three `RESTORED_ONLY_IDS` exist in the frozen collection exactly once,
   are disjoint from selected failure IDs, occur once only in
   `late-rejection-attribution`'s restored argv, and are absent from its mutated
   argv; and
8. the six corrected mappings are literal equality checks:
   `receipt-once-construction -> external::saved-main/receipt-count-55`,
   `diagnostics-sharing-reject -> SHARING_REJECT_ID`,
   `diagnostics-sharing-source-order -> SHARING_SOURCE_REJECTION_ID`,
   `group-dialog-owner-matrix -> GROUP_DIALOG_OWNERS_ID`,
   `group-own-dialog-matrix -> GROUP_OWN_DIALOG_ID`, and
   `marker-deferred-roster -> MARKER_DEFERRED_ID`; and
9. isolated `validate_identity_domains()` mutants reject a one-character typo in
   a future ID, any planned ID injected into `BASELINE_COLLECTED_IDS`, an
   undeclared non-baseline selected ID, a duplicate planned row, and each wrong
   module/function/parameter/task owner field at its own assertion. The
   unmodified exact 217/8 declaration then passes.

Serialize the complete registry deterministically with names, phases, exact
`worktree`/`scratch` edit roots, probe kinds, exact pytest IDs/non-pytest labels,
sentinels, regexes, forbidden rules,
edit paths plus old/new byte SHA-256 values, pytest argv, external
command/exit/stdout/stderr/sentinel-stream expectations, synthetic
callable/result/exception expectations, `RESTORED_ONLY_IDS`, and
`RESTORED_ONLY_BY_RECIPE`; write
`mutation-registry.json` and its SHA-256 beside the Task 1 artifacts. The Python
module, JSON manifest, phase tuples, restored-only mapping, canonical scratch
fixture bytes, and hash are frozen together before Task 3. `prepare_scratch_root`
creates a fresh disposable Git repository for the requested phase from those
bytes and returns its path; it never reuses a prior phase's dirty directory.
Later tasks may populate result records but may not add, rename, alias, or locally
reconstruct a recipe; an edit that cannot match the implemented or canonical
scratch bytes is a stop-and-correct-registry event, not permission for an ad hoc
mutation.

Step 4 creates `/tmp/stage-b-baseline/test_restore.py` and runs both tooling
suites only after `BASELINE_COLLECTED_IDS` is bound, in a disposable Git
repository. They must additionally prove all three dispatch paths plus
restoration after an intended generic probe failure; zero-match and two-match
literal rejection;
detection of bytes/hash/diff/status mismatch at exact `restoration bytes
mismatch`; exact-node mismatch rejection; longest-prefix parsing of a real
external pass, call failure, setup error, and parametrized node; property-list preservation; pytest call-phase/traceback/sentinel validation;
external exact exit/stdout/stderr/sentinel validation without JUnit; synthetic
exact callable result/exception/sentinel validation without JUnit; kind mismatch
rejection; sentinel mismatch rejection; and restored GREEN parsing.

This Task 1 evidence is **schema/name/regex/reference/owner smoke coverage for all
71**, plus generic runner restoration coverage. The generic disposable fixture
is not a registry edit/probe and is never reported as a Stage B defect. Task 1
does not execute any future implementation recipe. The actual bounded
representative recipes execute at their registered Task 3/4/5 phases once each
phase's real targets exist; all 71 real recipes likewise run only in Tasks 3–5.
Task 3 may not start until both Task 1 smoke suites pass, and Task 5 does not
report representative evidence until all seven actual subset variants have run
and restored successfully.

In this Step 2, compile only the collector/parser before it is used:

```bash
rm -rf /tmp/stage-b-baseline
mkdir -p /tmp/stage-b-baseline
# Materialize collector/ID-loader tooling now; registry/restoration files remain absent.
python -m py_compile \
  /tmp/stage-b-baseline/collect.py \
  /tmp/stage-b-baseline/test_collect.py
uv run --no-sync python -m pytest /tmp/stage-b-baseline/test_collect.py -q
bash /tmp/stage-b-baseline/test_ids.sh
test ! -e /tmp/stage-b-baseline/mutations.py
test ! -e /tmp/stage-b-baseline/restore.py
```

Add a `pytest_collection_finish` plugin in the same file. The path in
`STAGE_B_COLLECTION_REPORT` must end in `.collection.json`; the plugin writes one
deterministic UTF-8 JSON array, plus one final newline, whose ordered entries are
exactly:

```json
[{"nodeid":"tests/test_module.py::test_name[param]","markers":["parametrize"]}]
```

Each entry has exactly `nodeid,markers`; `nodeid` is a nonempty string without
CR/LF, and `markers` is a sorted unique list of nonempty strings. The report has
no duplicate node ID. Structured collection JSON is the only source for marker,
signature/owner, and mapping audits; it is never a pytest argument file and is
never hashed as an ordered-ID list.

`collect.py ids-from-collection INPUT.collection.json OUTPUT.ids.txt` is the one
conversion path. It revalidates the schema/uniqueness and writes UTF-8 bytes
`"".join(nodeid + "\\n" for nodeid in rows)`—one node ID and one LF per line,
with a final LF, no header, blank line, CR, or duplicate. `ids.sh` exposes
`load_ids INPUT.ids.txt ARRAY_NAME`; it rejects every other suffix, calls
`collect.py validate-ids`, and only then invokes `mapfile -t`. Every mapfile,
pytest argument-array expansion, ordered hash, and byte-equality check in this
plan uses a validated `.ids.txt`; distinct `*_REPORT` and `*_IDS` variable names
are mandatory. `test_collect.py` must reject malformed structured records,
blank/CR-containing IDs, duplicate IDs, a missing final LF, and any mismatch in
node IDs or order between a `.collection.json` report and its derived `.ids.txt`.
`test_ids.sh` must call `load_ids` with a valid ID file, then prove a structured
`.collection.json` path is rejected **before** its JSON can reach `mapfile`, and
prove blank-line and duplicate-ID `.ids.txt` fixtures are rejected.

Derive the 165 rows only from the six named test functions and parameter mapping
above; capture capture/dev program selection and saved-owner labels explicitly.
Write structured and ID-only pairs:

```text
/tmp/stage-b-baseline/target-205.collection.json
/tmp/stage-b-baseline/target-205.ids.txt
/tmp/stage-b-baseline/node-165.collection.json
/tmp/stage-b-baseline/node-165.ids.txt
/tmp/stage-b-baseline/helper-12.collection.json
/tmp/stage-b-baseline/helper-12.ids.txt
/tmp/stage-b-baseline/baseline-217.collection.json
/tmp/stage-b-baseline/baseline-217.ids.txt
/tmp/stage-b-baseline/node-map.json
/tmp/stage-b-baseline/shapes.json
```

Require exact counts `205/165/12`, uniqueness, the two frozen target hashes from
the corresponding `.ids.txt` bytes, and all four per-family counts
`62/65/17/21`. Assert from structured JSON that every marker, scenario, program,
protocol, label, signature owner, and timeout equals the approved spec, not
merely that totals match.

- [ ] **Step 3: Collect and bind exact 217 first, then capture one-shot evidence**

Run the collection/parser path before importing any registry module:

```bash
BASELINE_REPORT=/tmp/stage-b-baseline/target-helper-217.collection.json
PYTHONPATH=/tmp/stage-b-baseline \
  STAGE_B_COLLECTION_REPORT="$BASELINE_REPORT" \
  uv run --no-sync python -m pytest \
  tests/test_preview_savedlayouts_page.py \
  tests/test_fleetsharing_hydration.py \
  tests/test_preview_group_backward.py \
  tests/test_preview_labelmarkers_page.py \
  tests/test_node_scenario_worker.py \
  --collect-only -q -p no:cacheprovider -p collect
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  partition-baseline "$BASELINE_REPORT" /tmp/stage-b-baseline
for stem in target-205 node-165 helper-12 baseline-217; do
  uv run --no-sync python /tmp/stage-b-baseline/collect.py \
    ids-from-collection \
    "/tmp/stage-b-baseline/$stem.collection.json" \
    "/tmp/stage-b-baseline/$stem.ids.txt"
done
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  bind-baseline /tmp/stage-b-baseline/baseline-217.ids.txt
```

`partition-baseline` requires exactly 217 unique structured records in literal
collection order and writes only the four `.collection.json` reports plus
maps/shapes. The explicit conversion loop writes the four ID-only files. The
final command binds `BASELINE_COLLECTED_IDS` in `baseline_ids.py` only from
`baseline-217.ids.txt`. It requires the 205 target rows followed by the 12 helper
rows, exact 205/165 frozen hashes from ID-only bytes and `62/65/17/21` mapping
from structured records, and absence of all eight planned IDs. No registry/tooling
import is permitted before this command succeeds.

Immediately run the same exact 217 IDs once for outcomes through the already
materialized raw-JUnit parser:

```bash
source /tmp/stage-b-baseline/ids.sh
BASELINE_IDS_FILE=/tmp/stage-b-baseline/baseline-217.ids.txt
load_ids "$BASELINE_IDS_FILE" BASELINE_NODEIDS
uv run --no-sync python -m pytest "${BASELINE_NODEIDS[@]}" \
  -q -rs --junitxml=/tmp/stage-b-baseline/baseline-217.xml
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  verify-baseline-junit /tmp/stage-b-baseline/baseline-217.xml
```

Require `217 passed`, no skip/failure/error, and byte-for-byte JUnit identity
order equal to `baseline-217.ids.txt`. Do not infer node IDs from dotted classnames
by unconditional dot replacement. Use that same parser on the accepted Ubuntu
Stage A XML before registry materialization:

```bash
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  collection-from-junit \
  /mnt/c/dev/flygd-wingman/tmp/stage-a-hosted-36258907685/artifacts/ubuntu/pytest-result.xml \
  /tmp/stage-b-baseline/accepted-complete-16609.collection.json
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  ids-from-collection \
  /tmp/stage-b-baseline/accepted-complete-16609.collection.json \
  /tmp/stage-b-baseline/accepted-complete-16609.ids.txt
```

Require exactly 16,609 unique rows and final-newline hash
`f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100`.
Step 5 later re-audits full hosted provenance and retained bytes; this extraction
only supplies the already-approved frozen order needed by Step 4.

Only after `baseline_ids.py` exists, create
`/tmp/stage-b-baseline/probe_plugin.py`. Save the real functions before patching,
delegate every call, and restore in `pytest_unconfigure`:

```python
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

TARGET_PROGRAMS = {
    "preview_savedlayouts.cjs",
    "preview_capture_sessions.cjs",
    "preview_dev_capture.cjs",
    "fleetsharing_page.cjs",
    "preview_group_backward.cjs",
    "preview_labelmarkers.cjs",
}
REAL_RUN = subprocess.run
REAL_FSYNC = os.fsync
CURRENT = "<session>"
LAUNCHES = []
FSYNCS: dict[str, int] = {}


def recording_run(args, *positional, **keywords):
    result = REAL_RUN(args, *positional, **keywords)
    if isinstance(args, (list, tuple)) and len(args) > 1:
        program = Path(str(args[1])).name
        if program in TARGET_PROGRAMS:
            LAUNCHES.append({
                "nodeid": CURRENT,
                "program": program,
                "argv": [str(value) for value in args],
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            })
    return result


def recording_fsync(fd: int) -> None:
    FSYNCS[CURRENT] = FSYNCS.get(CURRENT, 0) + 1
    REAL_FSYNC(fd)


def pytest_sessionstart(session) -> None:
    subprocess.run = recording_run
    os.fsync = recording_fsync


def pytest_runtest_setup(item) -> None:
    global CURRENT
    CURRENT = item.nodeid


def pytest_runtest_teardown(item, nextitem) -> None:
    global CURRENT
    CURRENT = item.nodeid


def pytest_unconfigure(config) -> None:
    subprocess.run = REAL_RUN
    os.fsync = REAL_FSYNC
    root = Path(os.environ["STAGE_B_BASELINE_DIR"])
    (root / "one-shot.ndjson").write_text(
        "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in LAUNCHES),
        encoding="utf-8",
    )
    (root / "fsync.json").write_text(
        json.dumps({"counts": FSYNCS, "total": sum(FSYNCS.values())}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
```

Run all 205 existing rows once with this plugin. Require exactly 165 launches,
program counts `58/3/1/65/17/21`, zero nonzero exits, and exact streams. In
particular, ordinary successful programs have one PASS stdout line and empty
stderr; saved dev has 21 exact DEV stdout lines then `PASS dev`, plus one stderr
error beginning `onTheme handler failed TypeError: Cannot read properties of
undefined (reading 'apply')`; group dev has five DEV lines with one generated ID
repeated three times, then `PASS group backward dev`, and empty stderr; Fleet
Sharing `reject` and `bridge-source-rejection` still finish with only their PASS
stdout because their controlled errors are captured internally. Require fsync
`1,088` for all 205, `1,059` for the 165 Node rows, saved main `1,045`, owner
`10`, capture/dev `4`, and unchanged non-Node `29`.

- [ ] **Step 4: Materialize and smoke-test typed registry/restoration tooling**

Now—and only now—create `restore.py`, `mutations.py`, `test_restore.py`,
`test_mutations.py`, and `verify_task2_identities.py`. Each imports
`BASELINE_COLLECTED_IDS` from the Step 3 `baseline_ids.py`; none recollects or
reconstructs the baseline. Build the two frozen expected Task 2 order files and
the canonical registry manifest/hash, then run commands in this literal order:

```bash
test -f /tmp/stage-b-baseline/baseline_ids.py
test "$(wc -l < /tmp/stage-b-baseline/baseline-217.ids.txt)" -eq 217
python -m py_compile \
  /tmp/stage-b-baseline/restore.py \
  /tmp/stage-b-baseline/mutations.py \
  /tmp/stage-b-baseline/test_restore.py \
  /tmp/stage-b-baseline/test_mutations.py \
  /tmp/stage-b-baseline/verify_task2_identities.py
uv run --no-sync python /tmp/stage-b-baseline/verify_task2_identities.py \
  build-expected-collections
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  ids-from-collection \
  /tmp/stage-b-baseline/expected-task2-relevant-225.collection.json \
  /tmp/stage-b-baseline/expected-task2-relevant-225.ids.txt
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  ids-from-collection \
  /tmp/stage-b-baseline/expected-task2-complete-16617.collection.json \
  /tmp/stage-b-baseline/expected-task2-complete-16617.ids.txt
PYTHONPATH=/tmp/stage-b-baseline \
  uv run --no-sync python -m pytest \
  /tmp/stage-b-baseline/test_restore.py \
  /tmp/stage-b-baseline/test_mutations.py -q
uv run --no-sync ruff check /tmp/stage-b-baseline/*.py
uv run --no-sync ruff format --check /tmp/stage-b-baseline/*.py
```

This run is registry metadata/owner/kind/schema smoke plus disposable runner
coverage. It does not call phase-specific `validate_recipe()`, match edits
against not-yet-created Stage B implementation bytes, execute a canonical
mutation, or count as real-edit/representative defect qualification. Require
both expected `.collection.json` reports to match their derived
`expected-task2-relevant-225.ids.txt` and
`expected-task2-complete-16617.ids.txt` files row-for-row. Require the ID files to
have exact counts 225/16,617, unique rows, one final newline, exact approved
insertion anchors, and recorded SHA-256 values before continuing.

- [ ] **Step 5: Re-audit accepted Stage A hosted inputs and exact file hashes**

Materialize `/tmp/stage-b-baseline/hosted.py` by retaining the provenance,
artifact, JUnit, timing, skip-normalization, ZIP-member, and longest-module-prefix
functions from
`/mnt/c/dev/flygd-wingman/tmp/stage-a-hosted-36258907685/audit/audit_stage_a.py`,
but make its output read-only and point it at the Stage B worktree. Require:

```text
PR 291; run 36258907685; attempt 1
reviewed head 3c3fe622f2a178805f4267d90d12aff61293b6d7
frozen executable 83bd018b6eeb29e159741258e8d979c7481d7d01
base 463bccb07077325e64b6ad7f7ce4e9c100d2fcd6
synthetic 5e9adb83e8ac175756b987da25eeec657c4d1a4d
jobs checks/Ubuntu/Windows 108450833147/108450833121/108450833027
artifacts Ubuntu/Windows 10911184052/10911469146
16,609 unique IDs; hash f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100
Ubuntu 16,595 passed + 14 skipped
Windows 16,542 passed + 67 skipped
Ubuntu target 205 / Node 165 sums 20.521s / 20.454s
Windows target 205 / Node 165 sums 62.945s / 62.674s
```

Require these retained-byte SHA-256 values:

```text
49e8931d000f8c69041309136da481f86691c8f3fbca38093d5d4c4dd4c200f6  api/artifacts.json
dc477778b1e728ef6b13f445cc80ab4a3889a20574fa59a3206ed068c7949cf6  api/jobs-attempt-1.json
a1ee26101fa0d57d54c68cb0b61580a8870630c07c5004ebe10d7d3a42bdca7a  api/pr.json
e9c1038e3a0d71f4f24585ef259914b2450477da0f92ff64e542086a686bccec  api/run-attempt-1.json
d96d9edc7ba138023378678be970650ae48bb524e6c88cbdd278470cff16ad3c  api/run.json
6b6420e809e68479fac3d09f977ee357d17ddacc4a8ed13ecf6bc2aee8745de1  artifacts/downloads/ubuntu.zip
87ddd048aa4fce06cd0d8600b0e7435a4bf92be5240477f2b190259eccf5b1a1  artifacts/downloads/windows.zip
d424fc56070656e88e6c1791e34de59c5aeaea81527c456c18c1d5321291acf6  artifacts/ubuntu/pytest-result.xml
e41f9a0992dc1acfe028a92ebf02d6d057efd61e03d072315b92b9044c3cf6b7  artifacts/ubuntu/pytest-timing.json
ee15029ce8a392d7af526c39093c8781cc0ebcf0b0e643d8d860ca0e77f4f6d7  artifacts/windows/pytest-result.xml
f3b12200796084c028c11ae99f3115d48931c08880ca65379171054581afbce1  artifacts/windows/pytest-timing.json
c8da8682fb2eed9329f38c092de55012e6d92b85b15d548206e454ce0bcc0cea  audit/audit.json
c8da8682fb2eed9329f38c092de55012e6d92b85b15d548206e454ce0bcc0cea  audit/audit-output.json
dc08f0bfe6a9a410fd32da8ccac9d8cfd100ab3d7d1f3d6f94df0e9593f49e83  audit/audit_stage_a.py
9a4a809d770b9cb3783b00faeedbf6a1a4955bf3dd2f49304479ab65a9a6edb5  hosted-report.md
87cdc86e19823232ab03bfe552861ff6cb92fbecaa8e1912aa2a7bc7878fdd17  logs/attempt-1/108450833027.txt
26092ec07eac667843a36cd69c0d95fd87e900af7f8b19500f8647898a2bbf28  logs/attempt-1/108450833121.txt
041aa76d780fb56ecf3026fcf65130f1e368424e49bf5b9fa63809288599768b  logs/attempt-1/108450833147.txt
```

Write `/tmp/stage-b-baseline/hosted.json`, both ordered ID files, both normalized
skip JSON files, and an artifact hash manifest. Never edit the accepted evidence
directory.

- [ ] **Step 6: Freeze source hashes and exact structural shape**

Require the 13 hashes in the spec, including helper test hash
`dc8a2e9966f39efe5da2fee32e6af7072a925ca4ec624da50865e5139fa62aee`
and unchanged DOM hash
`c25e99234bb1e9856d8aa2d8c6cb910f1b68a55eb0c0a528508ab4a7c4eb5a8d`.
Record every test signature/decorator/marker and every CJS argv/PASS site. Also
freeze read-only protected hashes listed under Task 5.

- [ ] **Step 7: Create the baseline results ledger**

Create `docs/ci-persistent-page-workers-stage-b-results.md` with headings:

```text
Authority and exact source baseline
Accepted Stage A provenance and artifact hashes
Exact 205/165/12 identities and mappings
One-shot streams, launches, and timeouts
Baseline persistence arithmetic
TDD RED and GREEN record
Worker schema, VM, cleanup, and recovery qualification
Saved-layout receipt and family conversion
Remaining family conversion and order evidence
Mutation and restoration matrix
JUnit property ownership
Complete local endpoint
Reviews, final scope, and frozen heads
Publication stop and hosted evidence
Concerns and claim boundary
```

Populate only measured baseline values. Candidate, mutation, final-hash, and
hosted sections remain explicitly `not run in this task` sentences rather than
invented values.

- [ ] **Step 8: Verify and commit Task 1**

```bash
python -m py_compile /tmp/stage-b-baseline/collect.py /tmp/stage-b-baseline/test_collect.py /tmp/stage-b-baseline/probe_plugin.py /tmp/stage-b-baseline/hosted.py /tmp/stage-b-baseline/restore.py /tmp/stage-b-baseline/test_restore.py /tmp/stage-b-baseline/mutations.py /tmp/stage-b-baseline/test_mutations.py /tmp/stage-b-baseline/verify_task2_identities.py
uv run --no-sync python -m pytest /tmp/stage-b-baseline/test_collect.py /tmp/stage-b-baseline/test_restore.py /tmp/stage-b-baseline/test_mutations.py -q
bash /tmp/stage-b-baseline/test_ids.sh
uv run --no-sync ruff check /tmp/stage-b-baseline/*.py
uv run --no-sync ruff format --check /tmp/stage-b-baseline/*.py
uv run --no-sync python -m pytest tests/test_documentation.py -q
git diff --check
git add docs/ci-persistent-page-workers-stage-b-results.md
git diff --cached --name-only
git commit -m "docs: freeze persistent page worker baseline"
```

Expected staged path: only the results ledger. The commit is independently green.

---

### Task 2: Harden the Helper and Build the Shared Worker Foundation

**Files:**
- Modify: `tests/node_scenario_worker.py:3,445-466`
- Modify: `tests/test_node_scenario_worker.py:12-98,390-444`
- Create: `tests/fixtures/page_scenario_worker.cjs`
- Create: `tests/test_persistent_page_workers.py`
- Modify without converting a business caller: `tests/test_preview_savedlayouts_page.py:1-12` and a private provider inserted before line 13
- Modify: `docs/ci-persistent-page-workers-stage-b-results.md`

**Interfaces:**
- Consumes: unchanged `NodeScenarioWorker.request()` lifecycle, `PageTree`, `TextPageTree`, `SharingPageTree`, `Api`, `FakeWindow`, `make_state`, `pushes`, `owner_api`, `setup`, `drive`, `marker_choices`, and the seven startup source paths.
- Produces: strict `_validate_reply`; `page_scenario_worker.cjs --worker FAMILY WEB_ROOT MANIFEST_PATH`; synthetic qualification modes; seven exact qualification IDs; `_saved_layout_receipt_once(tmp_path_factory) -> SavedLayoutReceiptEvidence`.
- Does not yet replace any of the 165 business subprocess calls.

- [ ] **Step 1: Add one collectable helper RED**

Extend the test-local `WORKER_CJS` with a `numeric-schema` branch that can emit
raw nonfinite tokens without passing them through `JSON.stringify`:

```javascript
if (request.scenario === 'numeric-schema') {
  const mode = request.payload.mode;
  const id = mode === 'bool-id' ? 'true' : String(request.id);
  const durations = {
    'zero': '0',
    'float': '1.5',
    'bool-duration': 'true',
    'negative': '-1',
    'nan': 'NaN',
    'positive-infinity': 'Infinity',
    'negative-infinity': '-Infinity'
  };
  const duration = mode === 'bool-id' ? '0' : durations[mode];
  process.stdout.write('{"id":' + id
    + ',"scenario":"numeric-schema","ok":true,"duration_ms":'
    + duration + ',"error":"","stack":""}\n');
  return;
}
```

Add exactly one non-parametrized test immediately after the existing four
`test_invalid_reply_schema_discards_process_with_context_and_restarts` rows and
before `test_startup_failure_names_the_calling_scenario`, matching the Task 1
frozen insertion anchor:

```python
def test_reply_numeric_schema_rejects_bool_id_and_nonfinite_or_negative_duration(
    node_worker: NodeScenarioWorker,
):
    def rejected(mode: str, expected_error: str) -> None:
        if node_worker._proc is None:
            node_worker._ensure_started("numeric-schema")
        process = node_worker._proc
        request_id = node_worker._next_id
        assert process is not None
        try:
            node_worker.request("numeric-schema", {"mode": mode})
        except NodeScenarioCrash as crashed:
            assert expected_error in str(crashed), (
                f"numeric-schema {mode}: wrong protocol error"
            )
        else:
            pytest.fail(f"numeric-schema {mode}: invalid reply was accepted")
        termination_failure: AssertionError | None = None
        try:
            assert process.poll() is not None, (
                f"numeric-schema {mode}: rejected process was not terminated"
            )
        except AssertionError as error:
            termination_failure = error
        finally:
            # A discard mutant must fail immediately at poll(), not become a
            # five-second timeout, but the synthetic child still cannot leak.
            if process.poll() is None:
                node_worker._stop_process(process)
        if termination_failure is not None:
            raise termination_failure
        assert node_worker._proc is None, (
            f"numeric-schema {mode}: process was not discarded"
        )
        recovered = node_worker.request("echo-after-restart", {"text": mode})
        assert recovered["id"] == request_id + 1, (
            f"numeric-schema {mode}: recovery request ID was not monotonic"
        )
        assert node_worker._proc is not None
        assert node_worker._proc.pid != process.pid, (
            f"numeric-schema {mode}: recovery reused discarded PID"
        )

    rejected("bool-id", "reply field 'id' had the wrong type")

    try:
        zero = node_worker.request("numeric-schema", {"mode": "zero"})
    except NodeScenarioCrash as error:
        raise AssertionError("numeric-schema zero: valid duration rejected") from error
    assert zero["duration_ms"] == 0, "numeric-schema zero: valid duration changed"
    try:
        floating = node_worker.request("numeric-schema", {"mode": "float"})
    except NodeScenarioCrash as error:
        raise AssertionError("numeric-schema float: valid duration rejected") from error
    assert floating["duration_ms"] == 1.5, (
        "numeric-schema float: valid duration changed"
    )

    for mode in (
        "bool-duration",
        "negative",
        "nan",
        "positive-infinity",
        "negative-infinity",
    ):
        rejected(mode, "duration_ms")
```

The private `_ensure_started()` call creates process 1 without consuming request
ID 1. Consequently the bool-ID reply is valid in every other field, including
`duration_ms: 0`, and old `_validate_reply` accepts `true == 1`; RED is the exact
call-phase sentinel `numeric-schema bool-id: invalid reply was accepted` rather
than malformed JSON or ID mismatch. GREEN must reject and discard that process,
restart with request ID 2 and a distinct PID, accept integer zero and float 1.5,
and repeat the mode-qualified discard/restart proof for all five invalid
durations. The shared `rejected()` path inspects `poll()` immediately after
`request()` returns—there is no preceding `wait()`—and captures that assertion
before bounded cleanup in `finally`; therefore a discard mutant fails at exact
sentinel `numeric-schema bool-id: rejected process was not terminated` without a
five-second delay or leaked child. Every invalid schema mode uses this same
nonblocking termination pattern.

Also strengthen the unchanged existing `missing-fields` parameter case without
adding an ID: require exact crash text `reply missing 'id'`, then use explicit
`missing-fields reply did not use _ProtocolError` and
`missing-fields process was not discarded` assertion messages before its clean
ID-3/distinct-PID recovery. Collect it with the existing 12 IDs first. Run only
the new ID against the old validator in its own pytest process/JUnit file and
require exactly one collected testcase and one call-phase failure at the bool-ID
sentinel above. Reject import/collection/setup error or a failure caused by an
absent scenario branch. Complete this helper RED and Step 2 GREEN before creating
or executing any seven-ID qualification RED; their evidence is separate.

- [ ] **Step 2: Harden only `_validate_reply` and run all 13 helper IDs**

Add `import math` and replace only `_validate_reply` after its initial object
check with this complete ordering:

```python
        required = {
            "id": int,
            "scenario": str,
            "ok": bool,
            "duration_ms": (int, float),
            "error": str,
            "stack": str,
        }
        for key in required:
            if key not in payload:
                raise _ProtocolError(f"reply missing {key!r}")

        if type(payload["id"]) is not int:
            raise _ProtocolError("reply field 'id' had the wrong type")
        duration = payload["duration_ms"]
        if type(duration) not in (int, float):
            raise _ProtocolError("reply field 'duration_ms' had the wrong type")
        if duration < 0 or (type(duration) is float and not math.isfinite(duration)):
            raise _ProtocolError(
                "reply field 'duration_ms' was not finite and nonnegative"
            )
        for key in ("scenario", "ok", "error", "stack"):
            if not isinstance(payload[key], required[key]):
                raise _ProtocolError(f"reply field {key!r} had the wrong type")
        return dict(payload)
```

All six presence checks finish before any `payload[...]` access, so no missing
field can escape as `KeyError`; every rejected value raises `_ProtocolError` and
therefore reaches the existing discard path. Exact `type` checks exclude bool
for ID and duration without casting a large integer to float. Run all 13 IDs and
require the existing `missing-fields` discard/restart case plus late-exit phases
`before the next request`, `before replying to the next request`, `while sending the next request`, and `before close` remain exact.

- [ ] **Step 3: Add the receipt once-provider before wiring any page row**

In `tests/test_preview_savedlayouts_page.py`, add `gc`, `os`, `threading`,
`dataclass`, `replace`, `paths`, `Rect`, `Entry`, and
`PrimaryLayoutLiveResult` imports. Define:

```python
@dataclass(frozen=True)
class SavedLayoutReceiptEvidence:
    receipt_json: str
    durable_json: str
    keys: tuple[str, ...]
    fsync_calls: int
    created_id: str
    created_revision: str
    updated_revision: str
    renamed_revision: str
    pending_action: str
    pending_was_true: bool


_SAVED_LAYOUT_RECEIPT_LOCK = threading.Lock()
_SAVED_LAYOUT_RECEIPT: SavedLayoutReceiptEvidence | None = None


def _saved_layout_receipt_once(
    tmp_path_factory: pytest.TempPathFactory,
) -> SavedLayoutReceiptEvidence:
    global _SAVED_LAYOUT_RECEIPT
    with _SAVED_LAYOUT_RECEIPT_LOCK:
        if _SAVED_LAYOUT_RECEIPT is not None:
            return _SAVED_LAYOUT_RECEIPT
        _SAVED_LAYOUT_RECEIPT = _build_saved_layout_receipt(tmp_path_factory)
        return _SAVED_LAYOUT_RECEIPT
```

`_build_saved_layout_receipt()` must execute the exact 17-operation sequence in
the approved spec and preserve the current `apply_pending` implementation using
`api._fleet_worker.iterate_once()`, `pushes(api._window)`, and
`dataclasses.replace`. Build the dictionary in this exact insertion order:

```python
receipt = {
    "initial": initial,
    "hidden": hidden,
    "both": both,
    "visible": visible,
    "bulk": bulk,
    "pending": pending,
    "refused": refused,
    "retry": retry,
    "created": created,
    "duplicate": duplicate,
    "stale": stale,
    "updated": updated,
    "renamed": renamed,
    "removed": removed,
    "size_ack": size_ack,
    "geometry_apply": geometry_apply,
    "newer_geometry": newer_geometry,
    "newer_copy": newer_copy,
    "newer_reset": newer_reset,
    "failed_save": failed_save,
    "incomplete": incomplete,
    "unavailable": unavailable,
}
receipt_json = json.dumps(
    receipt,
    ensure_ascii=False,
    allow_nan=False,
    separators=(",", ":"),
)
```

Use a session path only from
`tmp_path_factory.mktemp("saved-layout-receipt")`; calling `make_state(tmp_path)`
or relying on function-scoped autouse isolation is explicitly insufficient for a
session provider. Capture the current presence/value of `LOCALAPPDATA`,
`paths._use_legacy`, `settings._save_locked`, `os.fsync`, and the current weak
reader entries before isolation. Enter a bounded outer
`pytest.MonkeyPatch.context()` that sets `LOCALAPPDATA` to the unique session
root, sets `paths._use_legacy = False`, and wraps the exact captured `os.fsync`
while delegating every call. The failed save uses a nested bounded patch context.
Validate `settings.paths.settings_file()` bytes as strict UTF-8 JSON, the
committed reader, pending first Apply, persisted final Apply, exact production
IDs/revisions, and 19 calls before shutdown.

In one outer `try/finally`, call `shutdown_previews()` for both APIs when created,
retain `weakref.ref` witnesses for every Stage-B-created Api/state/document/
committed-reader/controller object that supports weak references, delete bound
methods/controllers/readers and every other strong local owner, and call
`gc.collect()` before exposure. Exit both patch contexts, then prove the exact
prior environment presence/value, `paths._use_legacy`, `settings._save_locked`,
and `os.fsync` identities are restored. Require every Stage-B-owned weak witness
to be dead and no newly retained Stage-B reader key/value to remain in
`settings._COMMITTED_PREVIEWS`. Do **not** require unrelated weak keys observed
before setup to survive GC; their independent owners may disappear. Return only
the frozen dataclass above; no path, Api, state, document, reader, callback,
patch, or mutable receipt escapes.

- [ ] **Step 4: Add all seven qualification identities against a runnable unsafe RED seam**

Create `tests/test_persistent_page_workers.py` with exactly the seven IDs from
this plan and in their declared order: the four realm parameters, cleanup
success, cleanup failure, then receipt. Parametrize only the four realm rows
using:

```python
@pytest.mark.parametrize(
    "family",
    ["saved-layouts", "fleet-sharing", "group-backward", "label-markers"],
)
def test_request_realm_is_fresh_and_program_is_reexecuted(
    family, page_worker_factory, qualification_inputs, request
):
```

Do not add a parameter to either cleanup test. Define the module session input
bundle with this exact ownership signature:

```python
@pytest.fixture(scope="session")
def qualification_inputs(
    tmp_path_factory: pytest.TempPathFactory,
) -> QualificationInputs:
    return _build_qualification_inputs(tmp_path_factory)
```

`_build_qualification_inputs(tmp_path_factory)` owns the bounded context and
returns only after its cleanup assertions. The implementation may not replace
this with a `tmp_path` dependency. Every
provider in this module that constructs owner, capture, or settings state
must allocate a unique root with `tmp_path_factory.mktemp(...)`, then enter a
bounded `pytest.MonkeyPatch.context()` that sets `LOCALAPPDATA` to that root and
sets `paths._use_legacy = False` before the first `make_state(root)`/`owner_api`
call. Depending on `make_state(tmp_path)` alone is forbidden because the
function-scoped autouse fixtures do not isolate a session provider. Capture and
restore environment presence/value, `_use_legacy`, `_save_locked`, `os.fsync`,
and reader-registry ownership before returning anything. Shutdown every created
Api, detach owner `saved` and shared-capture payloads through strict finite JSON
bytes, release all state/document/reader/controller references, and run GC inside
the bounded cleanup. After GC require no newly retained Stage-B-owned weak reader
or owned-object reference; do not assert that unrelated old weak keys remain
alive. Only then expose immutable primitive inputs.

The bundle builds Text, structural, and Sharing page manifests and direct-CLI
representative payloads; it calls `_saved_layout_receipt_once(tmp_path_factory)`
rather than rebuilding the main receipt. Its extra real setup is exactly owner
`saved` (3 fsyncs) plus one shared capture input (1 fsync), reported by cleanup-
success as qualification-only `4`. The receipt's 19 calls remain owned by the
saved main `reversed` JUnit properties.

Before the real host exists, create a runnable temporary
`tests/fixtures/page_scenario_worker.cjs`. It accepts the exact worker argv,
opens the supplied manifest, reads NDJSON, and returns a syntactically and
schema-valid matching reply for every synthetic qualification request. It is
intentionally unsafe: it reports one reused realm/source counter, retained
cleanup state, and non-retainable business failure. It must not import any target
fixture and must not fail startup, collection, framing, or schema validation.
The receipt row uses a temporary in-process qualification seam that returns the
real provider's detached evidence plus `detached: false`; it does not skip or
raise during fixture setup.

Each test's first contract assertion is a real final invariant and owns one
literal call-phase RED sentinel:

```text
stage-b qualification realm saved-layouts: fresh execution violated
stage-b qualification realm fleet-sharing: fresh execution violated
stage-b qualification realm group-backward: fresh execution violated
stage-b qualification realm label-markers: fresh execution violated
stage-b qualification cleanup-success: retained resources
stage-b qualification cleanup-failure: process retention violated
stage-b qualification receipt: detachment violated
```

The tests already contain the remaining final assertions: A-poison-A same PID,
source execution count one per fresh realm, clean host prototypes, input/result
detachment, module-export isolation, zero cleanup, Error/primitive/hostile
getter/Proxy failures, Promise-then poison, timer/listener/unresolved-promise
cleanup, before/boundary rejection ownership, invalid business retention, fatal
protocol no retry, late-rejection phase/recovery, and exact worker-start evidence.
Task 3 switches saved to real execution and Task 4 switches the other three
without changing these IDs.

Collect first, then execute every ID independently through raw JUnit so one early
failure cannot hide another:

```bash
rm -rf /tmp/stage-b-task2-red
mkdir -p /tmp/stage-b-task2-red
QUALIFICATION_REPORT=/tmp/stage-b-task2-red/qualification-7.collection.json
QUALIFICATION_IDS_FILE=/tmp/stage-b-task2-red/qualification-7.ids.txt
PYTHONPATH=/tmp/stage-b-baseline \
  STAGE_B_COLLECTION_REPORT="$QUALIFICATION_REPORT" \
  uv run --no-sync python -m pytest tests/test_persistent_page_workers.py \
  --collect-only -q -p no:cacheprovider -p collect
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  ids-from-collection "$QUALIFICATION_REPORT" "$QUALIFICATION_IDS_FILE"
source /tmp/stage-b-baseline/ids.sh
load_ids "$QUALIFICATION_IDS_FILE" QUALIFICATION_NODEIDS
test "${#QUALIFICATION_NODEIDS[@]}" -eq 7
for index in "${!QUALIFICATION_NODEIDS[@]}"; do
  set +e
  uv run --no-sync python -m pytest "${QUALIFICATION_NODEIDS[$index]}" -q \
    --junitxml="/tmp/stage-b-task2-red/red-$index.xml"
  status=$?
  set -e
  test "$status" -eq 1
done
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  verify-qualification-red /tmp/stage-b-task2-red
```

Require exactly the seven frozen IDs. Each execution must collect one testcase
and produce exactly one call-phase `<failure>` at its own sentinel, with no
collection/setup/teardown error, skip, timeout, missing import, missing CJS file,
or cross-sentinel. Preserve the seven RED XML records and the temporary stub hash.
Step 5 completely replaces the unsafe CJS file and receipt seam with the real
implementation before GREEN; no stub branch, RED flag, or qualification bypass
may remain.

- [ ] **Step 5: Replace the RED stub with startup validation and the immutable source registry**

Overwrite the temporary unsafe `tests/fixtures/page_scenario_worker.cjs` in full;
do not layer production branches around the stub. Replace the temporary receipt
qualification seam with the real detached-evidence predicate. Require no RED
sentinel or unsafe marker remains, then require only builtins:

```javascript
'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
const vm = require('node:vm');
const {performance} = require('node:perf_hooks');
const {isNativeError} = require('node:util/types');
```

Validate argv exactly as `--worker FAMILY WEB_ROOT MANIFEST_PATH`. Define exact
family keys and label/protocol sets. Resolve and read all seven target paths with
`fs.readFileSync(file, 'utf8')` before stdin service, regardless of family. Read
only the production source union required by the selected family. Store source,
markup, pathname, and SHA-256 strings only; freeze the host registry. Validate
manifest version and exact page keys. Unknown family, malformed manifest, or
unreadable source writes one bounded stderr diagnostic and exits nonzero without
stdout.

The structural receipt returned only to qualification mode is:

```javascript
{
  source_manifest: sourceRows.map(({relative, source, sha256}) => ({
    path: relative,
    bytes: Buffer.byteLength(source, 'utf8'),
    sha256
  })),
  require_cache_targets: targetPaths.filter(file => require.cache[file]),
  module_child_targets: module.children
    .map(child => child.filename)
    .filter(file => targetPathSet.has(file)),
  retained_target_functions: 0
}
```

Assert the two target arrays are empty at startup and after each request. Never
write a target source to disk or call host `require()` on it.

- [ ] **Step 6: Implement strict request/failure classification**

Capture host JSON/string/object operations before serving. `validateRequest()`
requires exact envelope keys and adapter mapping. `assertFiniteJson()` recursively
rejects symbols/functions/bigints/nonfinite numbers, arrays with non-JSON values,
non-plain objects, and prototype-pollution keys before host reserialization.
Malformed NDJSON and validation failures call:

```javascript
function fatalProtocol(message, error = null) {
  const detail = error && isNativeError(error)
    ? message + ': ' + String(error.stack || error.message)
    : message;
  process.stderr.write(detail.slice(0, 65536) + '\n', () => process.exit(70));
}
```

Emit no reply. Do not catch this boundary and turn it into `ok:false`. Recognized
scenario plus semantically bad input enters the adapter and returns detached
`ok:false`, leaving the process live.

- [ ] **Step 7: Implement the fresh-VM bootstrap, VM-owned adapters, and poll loop**

For every valid request, create `vm.createContext(Object.create(null))`. Seed only
primitive JSON/source strings. The bootstrap captures pristine VM intrinsics,
deletes all seed globals, creates the assertion facade, structured console,
virtual timeout/interval/immediate scheduler, DOM factory, and these exact
VM-owned CommonJS substitutes:

```javascript
const sourceByBasename = JSON.parse(sourceRegistryJson);
const webByBasename = JSON.parse(webSourcesJson);
const decodedInput = safeParse(inputJson);
const contextRunners = new WeakMap();

function sameRealmRun(source, scope) {
  let runner = contextRunners.get(scope);
  if (!runner) {
    const factory = Function('scope', 'return (function* () {'
      + 'with (scope) { while (true) { const source = yield; eval(source); } }'
      + '})()');
    runner = factory(scope);
    runner.next();
    contextRunners.set(scope, runner);
  }
  return runner.next(source).value;
}

const fsFacade = Object.freeze({
  readFileSync(file, encoding) {
    assert.equal(encoding, 'utf8');
    const name = String(file).replaceAll('\\\\', '/').split('/').at(-1);
    if (name === 'request-input.json') return safeStringify(adapterInput);
    if (Object.hasOwn(webByBasename, name)) return webByBasename[name];
    throw new Error('Unknown fixture read ' + String(file));
  }
});
const vmFacade = Object.freeze({
  createContext(scope) { return scope; },
  runInContext(source, scope) { return sameRealmRun(source, scope); }
});
function runCommonJS(source, filename, requireFn) {
  const localModule = {exports: {}};
  const wrapper = Function(
    'require', 'module', 'exports', '__filename', '__dirname', source
  );
  wrapper(
    requireFn,
    localModule,
    localModule.exports,
    filename,
    filename.replace(/[/\\\\][^/\\\\]+$/, '')
  );
  return localModule.exports;
}
const domModule = runCommonJS(
  domFactorySource,
  domFactoryFilename,
  specifier => { throw new Error('Unknown DOM require ' + specifier); }
);
const createDOM = domModule.createDOM;
function localRequire(specifier) {
  if (specifier === 'node:assert/strict') return assertFacade;
  if (specifier === 'node:fs') return fsFacade;
  if (specifier === 'node:vm') return vmFacade;
  if (specifier === './screenshot_dom.cjs') return {createDOM};
  throw new Error('Unknown fixture require ' + specifier);
}
localRequire.main = Object.freeze({kind: 'persistent-page-worker'});
```

`module` and `exports` are created inside the request realm. Evaluate the
selected source through `runCommonJS(source, filename, localRequire)` and await
its exported completion inside the VM async body. The host must never receive
that promise. Build VM `process.argv` exactly as the direct CLI expects:

```text
saved-main/saved-owner/saved-capture/saved-dev:
  [node, fixture, request-input.json, WEB_ROOT]
fleet-sharing:
  [node, fixture, request-input.json, SCENARIO, WEB_ROOT]
group-backward/label-markers:
  [node, fixture, request-input.json, WEB_ROOT]
```

The VM-owned `process` permits only mutable `exitCode` plus those primitive argv
strings; it exposes no stdout, stderr, environment, native handles, or exit
function.

The bootstrap returns one VM-owned `poll(now, mailboxJson)` function. No host
function remains in the VM after bootstrap. `poll` dispatches due virtual timers
inside the VM, consumes only primitive rejection/dispatch records, advances the
post-business microtask plus one-zero-delay-turn boundary, cancels all virtual
handles/listeners, serializes with captured intrinsics, and returns either `null`
or one primitive reply JSON string. The host calls it with `performance.now()`
and primitive mailbox JSON, yielding with host `setImmediate`; it never receives
a VM callback and never injects a native timer handle.

- [ ] **Step 8: Implement rejection ownership and defensive detachment**

Install one request listener before VM launch and keep one process-level fail-fast
listener. The request listener ignores the promise argument and immediately
serializes the reason through the originating VM:

```javascript
function serializeOpaqueVmFailure(runtime, reason) {
  const token = crypto.randomBytes(16).toString('hex');
  const slot = '__wingmanOpaqueFailure_' + token;
  runtime[slot] = reason;
  try {
    const serialized = vm.runInContext(buildFailureSerializer(slot), runtime);
    return parseBoundedFailureJson(serialized);
  } finally {
    delete runtime[slot];
  }
}

const captureRejection = reason => {
  rejectionMailbox.push(serializeOpaqueVmFailure(runtime, reason));
};
```

`buildFailureSerializer()` captures VM `String`, reads `name/message/stack`
independently under `try/catch`, emits bounded primitive JSON, and deletes its
reason/serializer slots in its own `finally`. No host getter/coercion touches the
reason; no raw reason or promise enters an array or closure. Timer dispatch catches
and serializes in the same realm immediately.

Before/boundary rejection records replace success with `ok:false` and same-PID
recovery. After cleanup set the active request to null before publishing. The
process listener treats any later rejection as fatal, writes
`late unhandled rejection after published success`, and exits nonzero. The serial
read loop waits one post-reply event-loop turn before accepting the next line.

Return exact additive fields:

```javascript
{
  id: request.id,
  scenario: request.scenario,
  ok,
  duration_ms: performance.now() - started,
  output,
  error,
  stack,
  diagnostics,
  cleanup: {
    host_timer_handles: 0,
    host_callbacks: 0,
    active_rejection_listeners: 0,
    pending_rejection_records: 0,
    retained_realms: 0
  }
}
```

A cleanup, serializer, double-completion, or detachment proof failure calls
`fatalProtocol` and emits no success reply.

- [ ] **Step 9: Complete the seven qualification tests and direct CLI matrix**

The four realm cases use representative protocol/scenario pairs from the spec.
Each performs real-or-synthetic A, a synthetic poison that also executes the
selected program when available, and A again in one PID. Poison global,
`Object/Array/Promise/Error` and DOM prototypes, `Promise.prototype.then`, decoded
input, prior reply, diagnostics arguments, `module.exports`, and cached-output
sentinel; assert source execution counter `1` in each fresh realm.

`test_request_cleanup_after_success` runs timer/interval/immediate, DOM/window
listener, unresolved-promise, source-manifest/cache/children/export-poison, and
six direct-CLI internal subcases. For every existing CJS script run:

1. representative success with exact argv, exit zero, exact terminal, and exact
   stdout/stderr contract;
2. missing required argv, nonzero, no stdout/PASS, nonempty stderr usage/load
   diagnostic;
3. minimally corrupt JSON input, nonzero, no terminal PASS, diagnostic/stack on
   stderr; ordinary dev logs before failure may remain stdout.

Also run saved `owner-controls`. Pin all 21 saved-dev lines, one known theme error
with detached third argument, five group-dev lines and generated-ID equality,
Fleet reject/source-rejection diagnostic count/order/method/message, and zero
controlled errors elsewhere. Persistent output is the terminal without newline;
PASS does not appear in diagnostics.

`test_request_cleanup_after_business_failure` runs Error, primitive, null,
hostile getters, throwing Proxy, invalid recognized business input, before
settlement rejection, timer-boundary rejection, one fatal request, and one late
post-success rejection. After every retainable failure, assert a clean request in
the same PID. This permanent identity exercises exactly one representative fatal request: a
family-valid scenario whose payload object is missing the required `input` key.
Process A (worker start 1) serves all retainable failures and dies on that fatal
without replay; a separate call starts process B (start 2), whose
successful `S` schedules the late exit; `T` observes B's exit, fails with
`.scenario == T`, exact `before the next request`, and prior `S`/request `N`
without starting or executing a replacement; only the following recovery call
starts process C (start 3), uses ID `N+2`, and succeeds. Assert and publish
`stage_b.qualification.worker_starts == 3` from these three observed PIDs—no
other fatal variant runs inside this identity.

Malformed NDJSON, wrong-family label, unknown protocol, and unknown scenario are
qualified later by four independent `/tmp` variant probes. Each gets a fresh
process, exact input bytes, exact no-valid-reply/nonzero-exit assertion, its own
literal mutation and unique sentinel, and a separate clean-process recovery.
Their process starts are mutation/probe overhead in the results ledger and are
never added to, or described by, the permanent cleanup-failure value `3`.

`test_saved_layout_receipt_is_durable_and_detached` consumes the private once-
provider, asserts exact 22-key order, strict finite JSON, 19 fsyncs, durable JSON,
restored environment/legacy/writer identities, no newly retained Stage-B-owned
reader or owned-object weak references after GC, production ID/revision
continuity, pending first Apply, final persisted Apply, 55 independent decodes,
and no alias after mutating one. It does not require unrelated pre-existing weak
registry entries to survive.

- [ ] **Step 10: Run Task 2 GREEN, enforce the post-creation identity gate, and commit**

```bash
TASK2_RELEVANT_REPORT=/tmp/stage-b-baseline/task2-relevant-225.collection.json
TASK2_RELEVANT_IDS=/tmp/stage-b-baseline/task2-relevant-225.ids.txt
TASK2_COMPLETE_REPORT=/tmp/stage-b-baseline/task2-complete-16617.collection.json
TASK2_COMPLETE_IDS=/tmp/stage-b-baseline/task2-complete-16617.ids.txt
rm -f \
  "$TASK2_RELEVANT_REPORT" "$TASK2_RELEVANT_IDS" \
  "$TASK2_COMPLETE_REPORT" "$TASK2_COMPLETE_IDS"
node --check tests/fixtures/page_scenario_worker.cjs
uv run --no-sync python -m pytest tests/test_node_scenario_worker.py -q -rs
uv run --no-sync python -m pytest tests/test_persistent_page_workers.py -q -rs
uv run --no-sync python -m pytest \
  tests/test_node_scenario_worker.py \
  tests/test_persistent_page_workers.py \
  -q -rs --junitxml=/tmp/stage-b-task2.xml
PYTHONPATH=/tmp/stage-b-baseline STAGE_B_COLLECTION_REPORT="$TASK2_RELEVANT_REPORT" \
  uv run --no-sync python -m pytest \
  tests/test_preview_savedlayouts_page.py \
  tests/test_fleetsharing_hydration.py \
  tests/test_preview_group_backward.py \
  tests/test_preview_labelmarkers_page.py \
  tests/test_node_scenario_worker.py \
  tests/test_persistent_page_workers.py \
  --collect-only -q -p no:cacheprovider -p collect
PYTHONPATH=/tmp/stage-b-baseline STAGE_B_COLLECTION_REPORT="$TASK2_COMPLETE_REPORT" \
  uv run --no-sync python -m pytest tests/ \
  --collect-only -q -p no:cacheprovider -p collect
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  ids-from-collection "$TASK2_RELEVANT_REPORT" "$TASK2_RELEVANT_IDS"
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  ids-from-collection "$TASK2_COMPLETE_REPORT" "$TASK2_COMPLETE_IDS"
uv run --no-sync python /tmp/stage-b-baseline/verify_task2_identities.py \
  "$TASK2_RELEVANT_REPORT" "$TASK2_RELEVANT_IDS" \
  "$TASK2_COMPLETE_REPORT" "$TASK2_COMPLETE_IDS"
uv run --extra dev ruff check tests/node_scenario_worker.py tests/test_node_scenario_worker.py tests/test_preview_savedlayouts_page.py tests/test_persistent_page_workers.py
uv run --extra dev ruff format --check tests/node_scenario_worker.py tests/test_node_scenario_worker.py tests/test_preview_savedlayouts_page.py tests/test_persistent_page_workers.py
git diff --check
git add tests/node_scenario_worker.py tests/test_node_scenario_worker.py tests/fixtures/page_scenario_worker.cjs tests/test_persistent_page_workers.py tests/test_preview_savedlayouts_page.py docs/ci-persistent-page-workers-stage-b-results.md
git diff --cached --name-only
git commit -m "test: add persistent page worker foundation"
```

Expected runtime outcome: 13 helper IDs and seven qualification IDs pass; no
business family has been migrated; existing 217 rows remain green. Record
synthetic qualification as staged foundation evidence, not final real-family
acceptance.

`verify_task2_identities.py` is the hard pre-Task-3 gate. It imports the actual
Task 1 declarations and requires:

- fresh `task2-relevant-225.ids.txt` is byte-for-byte equal to frozen
  `expected-task2-relevant-225.ids.txt`, including one final newline—not merely an
  old-ID subsequence plus an additions set;
- fresh `task2-complete-16617.ids.txt` is byte-for-byte equal to frozen
  `expected-task2-complete-16617.ids.txt`, including exact module-local insertion
  positions—not merely the accepted 16,609 as a subsequence;
- both actual ID-only files have unique IDs and exact counts 225/16,617; their
  corresponding structured reports match them row-for-row and supply marker and
  owner evidence; all eight additions occur once with the declared
  module/function/parameter owner, all
  217 baseline IDs retain exact order, and the frozen 205/165/12 subsets and
  hashes remain unchanged;
- the expected and fresh-actual ordered final-newline SHA-256 values are equal,
  then the actual bytes/hashes are frozen in
  `/tmp/stage-b-baseline/task2-identity-gate.json` plus the results ledger; and
- the gate records hashes of the two new/changed test modules, canonical registry
  JSON/hash, all four structured-report/ID-file pairs, exact counts, ID-only
  expected/actual ordered hashes, row-for-row report/ID agreement, and empty
  symmetric differences.

A future ID may be absent only during the Task 1 declaration check. After Task 2,
all eight must be actually collectable exactly once and in frozen order. A typo,
missing ID, duplicate, wrong owner/parameter, insertion-order drift, count drift,
or collection error stops before commit and before any Task 3 registry consumer.

---

### Task 3: Convert the Complete Saved-Layout Family

**Files:**
- Modify: `tests/test_preview_savedlayouts_page.py:1-289`
- Modify: `tests/fixtures/preview_savedlayouts.cjs:1-657`
- Modify: `tests/fixtures/preview_capture_sessions.cjs:1-77`
- Modify: `tests/fixtures/preview_dev_capture.cjs:1-69`
- Modify: `tests/test_persistent_page_workers.py`
- Modify: `docs/ci-persistent-page-workers-stage-b-results.md`

**Interfaces:**
- Consumes: the passing `/tmp/stage-b-baseline/task2-identity-gate.json`,
  `NodeScenarioWorker`, `page_scenario_worker.cjs`,
  `_saved_layout_receipt_once()`, Text/structural page trees, and protocols
  `saved-main`, `saved-owner`, `saved-capture`, `saved-dev`.
- Produces: `saved_layout_page_worker`, immutable
  `saved_layout_receipt_bytes`, 62 worker requests, one family PID, and receipt
  build/fsync JUnit ownership.

- [ ] **Step 1: Revalidate the Task 2 identity gate, then add the saved-family fixture substitutions as collectable RED**

Before editing, rerun both Task 2 structured collection commands, both explicit
`ids-from-collection` conversions, and `verify_task2_identities.py`. Require each
fresh report/ID pair to agree row-for-row and both fresh `.ids.txt` files to
remain byte-for-byte equal to the frozen actual Task 2 ID files and their expected
ID files, with the same 225/16,617 counts, ordered ID-file hashes, owners, and empty symmetric
differences recorded in `task2-identity-gate.json`. Also require the recorded
test-module and registry hashes to match the current tree. This is a hard gate:
no Task 3 recipe or source edit starts if it fails.

Then create the manifest and worker fixtures:

```python
ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wingman/web"


@pytest.fixture(scope="session")
def saved_layout_page_worker(tmp_path_factory: pytest.TempPathFactory):
    text_tree = TextPageTree()
    text_tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    structural_tree = PageTree()
    structural_tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    manifest = tmp_path_factory.mktemp("saved-layout-page-worker") / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"version": 1, "pages": {"text": text_tree.root, "structural": structural_tree.root}},
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    node = shutil.which("node")
    assert node is not None, "node is not installed"
    worker = NodeScenarioWorker(
        [node, str(ROOT / "tests/fixtures/page_scenario_worker.cjs"), "--worker", "saved-layouts", str(WEB), str(manifest)],
        cwd=ROOT,
    )
    try:
        yield worker
    finally:
        worker.close()


@pytest.fixture(scope="session")
def saved_layout_receipt_bytes(
    tmp_path_factory: pytest.TempPathFactory,
) -> bytes:
    return _saved_layout_receipt_once(tmp_path_factory).receipt_json.encode("utf-8")
```

Add the module-local autouse direct-fsync fixture. It captures and delegates the
real `os.fsync`, counts only function-scope calls, and in `finally` appends one
`stage_b.direct_fsync_calls` property. Higher-scoped manifest/receipt setup must
finish before this fixture starts. Add `_record_saved_worker()` to append family,
PID, and reply ID once, plus the two receipt properties only when
`request.node.nodeid` is exact saved-main `reversed`.

The saved-main conversion replaces the **entire** current function body—not only
its subprocess tail. The exact baseline body removed is:

```python
def test_saved_layout_page_ordering(tmp_path, scenario, monkeypatch):
    state = make_state(tmp_path)
    with settings.update(state.settings) as doc:
        doc.setdefault("preview", {}).update(seen=["Alice", "Bob"])
    api = Api(state)
    api._window = FakeWindow()
    from wingman.preview.geometry import Rect
    from wingman.preview.layout import Entry

    api._preview_layout_store.replace("Alice", Entry(Rect(1, 2, 500, 300)))
    initial = api.get_preview_hotkey_state()
    hidden = api.set_preview_excluded("Alice", True)
    both = api.set_preview_excluded("Bob", True)
    created = api.create_preview_layout("Hidden")
    record = created["state"]["layouts"][0]
    api.set_preview_excluded("Bob", False)
    visible = api.set_preview_excluded("Alice", False)
    # A blocked native boundary lets the real shared presentation owner sample
    # pending state deterministically; coalescing need not replay every transition.
    pending_states = []
    original = api._apply_preview_layout
    from dataclasses import replace

    def apply_pending(*args):
        api._fleet_worker.iterate_once()
        pending_states.extend(
            payload
            for handler, payload in pushes(api._window)
            if handler == "onPreviewLayouts" and payload["operation"]["pending"]
        )
        return original(*args)

    api._preview_layouts._ports = replace(
        api._preview_layouts._ports, apply=apply_pending
    )
    bulk = api.apply_preview_layout(record["id"], record["revision"])
    pending = pending_states[-1]
    lease = api._preview_layout_admission.try_begin(exclusive=True)
    refused = api.set_preview_excluded("Alice", False)
    api._preview_layout_admission.finish(lease)
    retry = api.set_preview_excluded("Alice", False)
    size_ack = api.set_preview_size("Alice", 600, 400)
    geometry_apply = api.apply_preview_layout(record["id"], record["revision"])
    api.set_preview_size("Alice", 700, 450)
    newer_geometry = api._sample_preview_geometry()
    api._preview_layout_store.replace("Bob", Entry(Rect(5, 6, 640, 480)))
    api.copy_preview_layout("Alice", "Bob")
    newer_copy = api._sample_preview_geometry()
    api.reset_preview_layouts()
    newer_reset = api._sample_preview_geometry()
    duplicate = api.create_preview_layout("HIDDEN")
    stale = api.apply_preview_layout(record["id"], "stale")
    updated = api.update_preview_layout(record["id"], record["revision"])
    updated_record = updated["state"]["layouts"][0]
    renamed = api.rename_preview_layout(
        updated_record["id"], updated_record["revision"], "__proto__"
    )
    renamed_record = renamed["state"]["layouts"][0]
    removed = api.remove_preview_layout(
        renamed_record["id"], renamed_record["revision"]
    )
    with monkeypatch.context() as patch:

        def fail_save(*args, **kwargs):
            raise OSError("Disk unavailable")

        patch.setattr(settings, "_save_locked", fail_save)
        failed_save = api.create_preview_layout("Refused")
    from wingman.preview.savedlayouts import PrimaryLayoutLiveResult

    api._preview_layouts._ports = replace(
        api._preview_layouts._ports,
        refresh_visibility=lambda lease: api._settled_preview_layout(
            PrimaryLayoutLiveResult(
                "incomplete", "Saved, but one preview could not be shown."
            )
        ),
    )
    incomplete = api.set_preview_excluded("Alice", False)
    empty_api = Api(make_state(tmp_path))
    unavailable = empty_api.get_preview_hotkey_state()
    web = Path(__file__).parents[1] / "wingman/web"
    data = tmp_path / "page.json"
    tree = TextPageTree()
    tree.feed((web / "index.html").read_text(encoding="utf-8"))
    data.write_text(
        json.dumps(
            {
                "scenario": scenario,
                "page": tree.root,
                "initial": initial,
                "hidden": hidden,
                "both": both,
                "visible": visible,
                "bulk": bulk,
                "pending": pending,
                "refused": refused,
                "retry": retry,
                "created": created,
                "duplicate": duplicate,
                "stale": stale,
                "updated": updated,
                "renamed": renamed,
                "removed": removed,
                "size_ack": size_ack,
                "geometry_apply": geometry_apply,
                "newer_geometry": newer_geometry,
                "newer_copy": newer_copy,
                "newer_reset": newer_reset,
                "failed_save": failed_save,
                "incomplete": incomplete,
                "unavailable": unavailable,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "node",
            str(Path(__file__).parent / "fixtures/preview_savedlayouts.cjs"),
            str(data),
            str(web),
        ],
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS " + scenario in result.stdout
```

Replace it exactly with:

```python
def test_saved_layout_page_ordering(
    saved_layout_page_worker,
    saved_layout_receipt_bytes,
    request,
    scenario,
):
    input_payload = json.loads(saved_layout_receipt_bytes.decode("utf-8"))
    input_payload["scenario"] = scenario
    input_payload["page"] = "text"
    reply = saved_layout_page_worker.request(
        f"preview-saved-layouts/page/{scenario}",
        {"protocol": "saved-main", "input": input_payload},
        timeout=25.0,
    )
    assert reply["output"] == f"PASS {scenario}"
    assert reply["cleanup"] == ZERO_CLEANUP
    _record_saved_worker(request, saved_layout_page_worker, reply)
```

The primitive `page="text"` selects the startup manifest entry; the worker
replaces it with a fresh VM-side decode before evaluating the fixture. The final
saved-main function has no `tmp_path` or `monkeypatch` fixture, creates no state,
Api, receipt value, page tree, data file, or subprocess, and decodes the immutable
receipt bytes afresh for every row.

Extend the AST/signature gate with one literal exception record for exactly
`(saved_layout_page_worker, saved_layout_receipt_bytes, request, scenario)`.
Require the decorator AST to remain byte-for-AST equal, and require the final
function AST to contain none of `make_state`, `Api`, `settings.update`,
`TextPageTree`, `subprocess.run`, `tmp_path`, or `monkeypatch`. For owner and
capture rows only, keep their own production setup and assertions and replace
only their subprocess blocks: owner passes `source`, `initial`, `marker`,
`visible`, and `copied` and expects `PASS owner-controls`; capture passes
`scenario` and real `initial`, selecting `saved-dev` only for `dev`.

Run collection and require all 62 IDs unchanged. Run `reversed`, owner `saved`,
capture `reversed`, and dev; RED must be a business source completion-export
failure, not collection/import/setup failure.

- [ ] **Step 2: Make the three CJS files dual-entry without changing assertions**

For each file, leave imports, data/DOM/bridge setup, scenario branches, and PASS
`console.log` statements unchanged. Name the async result and export it only when
evaluated as a module:

```javascript
const scenarioCompletion = (async () => {
  // Existing body remains byte-for-behavior unchanged.
})();
if (require.main === module) {
  scenarioCompletion.catch(error => {
    console.error(error);
    process.exitCode = 1;
  });
} else {
  module.exports = scenarioCompletion;
}
```

For `preview_capture_sessions.cjs`, retain its existing no-space catch formatting
only if stream snapshots prove that formatting matters; behavior is identical.
The worker's VM-owned `require.main` sentinel differs from VM-owned `module`, so
it awaits `module.exports` inside the VM. Direct Node execution takes the original
catch path. The worker extracts exactly one terminal PASS diagnostic into
`output`, removes it from diagnostics, and retains all preceding logs/errors.

- [ ] **Step 3: Switch the saved qualification representative from synthetic to real**

The `saved-layouts` realm row uses `saved-main/reversed` and a fresh decode of the
once receipt. Poison runs the real program before mutating realm/module/input/
result state. The cleanup-success direct matrix continues to invoke all three
saved CJS paths directly and also invokes `preview_savedlayouts.cjs` with the real
owner-controls input.

- [ ] **Step 4: Run saved GREEN and exact count/property checks**

Run all 62 in collected order with raw JUnit. Require all pass, one positive PID,
request IDs `1..62`, exact outputs, zero cleanup, Node starts `62 -> 1`, direct
fsync sum `14`, one receipt property owner with 19, and total saved candidate
`19 + 14 = 33`. Run each of the four program representatives alone in fresh
pytest invocations; each starts exactly one process and closes it.

- [ ] **Step 5: Run saved order and isolation sequences**

Materialize exact 62-ID `normal.ids.txt`, `reverse.ids.txt`, and
`shuffle-20260926.ids.txt` files through the canonical ID writer/validator. Load
each pytest argument array through `load_ids` and execute it in a fresh process;
require 62 passes, one family PID,
request ordinals `1..62`, 33 total fsyncs, and exact output/diagnostic parity.
Within one process run:

```text
saved-main/reversed -> saved-owner/saved -> saved-capture/boundary -> saved-dev/dev -> saved-main/reversed
```

Require A-B-A equality except the documented generated dev ID, one PID, fresh
execution counter one per request, and zero cleanup. Record the deterministic
shuffle hash only after writing the exact final-newline list.

- [ ] **Step 6: Run the saved/receipt/realm mutation slice**

Load the canonical Task 1 registry and execute `TASK3_RECIPES` in its declared
order. This phase references recipe names only; exact typed pytest IDs or probe
labels, literal sentinels/anchored regexes, forbidden masking, byte edits, mutated probes, and
restored probes come exclusively from `REGISTRY`. Before the first mutation,
require
`validate_registry(worktree, BASELINE_COLLECTED_IDS, phase="task3",
scratch_root=prepare_scratch_root("task3"))` to match every Task 3 old literal
exactly once in its declared root. After each recipe, restore
bytes/hash/diff/status and run
its registry-owned restored probe through the typed dispatcher. The saved
`reversed` anti-mask case is already part of the relevant
`PytestProbe.restored_argv`, not a second prose recipe; the external receipt-count
recipe instead uses its exact registered restored command/exit/stdout/stderr.
Write one result per canonical name and reject a missing, duplicate, or extra
Task 3 result. Every result records `kind` plus kind-specific evidence: pytest
IDs/JUnit phase/traceback, external command/exit/stdout/stderr, or synthetic
callable/result/exception.

- [ ] **Step 7: Commit the independently green saved family**

```bash
node --check tests/fixtures/page_scenario_worker.cjs
node --check tests/fixtures/preview_savedlayouts.cjs
node --check tests/fixtures/preview_capture_sessions.cjs
node --check tests/fixtures/preview_dev_capture.cjs
uv run --no-sync python -m pytest tests/test_preview_savedlayouts_page.py tests/test_persistent_page_workers.py -q -rs
uv run --extra dev ruff check tests/test_preview_savedlayouts_page.py tests/test_persistent_page_workers.py
uv run --extra dev ruff format --check tests/test_preview_savedlayouts_page.py tests/test_persistent_page_workers.py
git diff --check
git add tests/test_preview_savedlayouts_page.py tests/fixtures/preview_savedlayouts.cjs tests/fixtures/preview_capture_sessions.cjs tests/fixtures/preview_dev_capture.cjs tests/test_persistent_page_workers.py docs/ci-persistent-page-workers-stage-b-results.md
git diff --cached --name-only
git commit -m "test: reuse saved layout page worker"
```

---

### Task 4: Convert Fleet Sharing, Group Backward, and Label Markers

**Files:**
- Modify: `tests/test_fleetsharing_hydration.py:1-213`
- Modify: `tests/test_preview_group_backward.py:1-471`
- Modify: `tests/test_preview_labelmarkers_page.py:1-64`
- Modify: `tests/fixtures/fleetsharing_page.cjs:1-1041`
- Modify: `tests/fixtures/preview_group_backward.cjs:1-473`
- Modify: `tests/fixtures/preview_labelmarkers.cjs:1-351`
- Modify: `tests/test_persistent_page_workers.py`
- Modify: `docs/ci-persistent-page-workers-stage-b-results.md`

**Interfaces:**
- Consumes: shared worker protocols `fleet-sharing`, `group-backward`, and
  `label-markers`, family manifests, current Python production fixture inputs,
  and exact direct CLI wrappers.
- Produces: `fleetsharing_page_worker`, `group_backward_page_worker`,
  `labelmarkers_page_worker`, all 103 remaining worker rows, and final four-family
  qualification.

- [ ] **Step 1: Add three session manifests/workers and collectable RED conversions**

Use the same worker construction/close pattern as Task 3 with exact manifest
pages:

```python
@pytest.fixture(scope="session")
def fleetsharing_page_worker(tmp_path_factory: pytest.TempPathFactory):
    tree = SharingPageTree()
    tree.feed((WEB / "index.html").read_text(encoding="utf-8"))
    yield from _family_worker_fixture(
        tmp_path_factory, "fleet-sharing", {"sharing": tree.root}
    )
```

Because helper generators cannot be moved outside the 17-path scope, define the
small `_family_worker_fixture()` locally in each module rather than importing a
test fixture. Group and marker use `PageTree` plus `{"structural": tree.root}`.
Each fixture uses `shutil.which("node")` and asserts availability; none skips.
Each module adds its own autouse direct-fsync recorder and worker-property helper.

Fleet Sharing retains its production setup and therefore its approved `tmp_path`
fixture. Its final signature is exactly:

```python
def test_sharing_watch_runtime(
    tmp_path, fleetsharing_page_worker, request, scenario
):
```

Keep the body from `api = Api(make_state(...))` through construction of
`preference_case` and both `finally` shutdown assertions. Replace the exact tail
beginning `page = SharingPageTree()` through the subprocess PASS assertion with:

```python
        reply = fleetsharing_page_worker.request(
            f"fleet-sharing/page/{scenario}",
            {
                "protocol": "fleet-sharing",
                "input": {
                    "scenario": scenario,
                    "page": "sharing",
                    "missing": api.fleet_sharing_watch(True),
                    "live": live_api.fleet_sharing_state(),
                    "older": older,
                    "rejected": rejected,
                    "preference_case": preference_case,
                },
            },
            timeout=20.0,
        )
        assert reply["output"] == f"PASS {scenario}"
        assert reply["cleanup"] == ZERO_CLEANUP
        _record_fleetsharing_worker(
            request, fleetsharing_page_worker, reply
        )
```

The group conversion replaces this exact complete baseline function body:

```python
def test_group_backward_page(tmp_path, scenario):
    from tests.html_tree import PageTree
    from wingman.preview.labelmarkers import marker_choices

    root = Path(__file__).resolve().parents[1]
    tree = PageTree()
    tree.feed((root / "wingman/web/index.html").read_text(encoding="utf-8"))
    data = tmp_path / "group-backward.json"
    data.write_text(
        json.dumps(
            {"page": tree.root, "choices": marker_choices(), "scenario": scenario}
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "node",
            str(root / "tests/fixtures/preview_group_backward.cjs"),
            str(data),
            str(root / "wingman/web"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS group backward {scenario}" in result.stdout
```

Replace it exactly with:

```python
def test_group_backward_page(group_backward_page_worker, request, scenario):
    from wingman.preview.labelmarkers import marker_choices

    choices = json.loads(
        json.dumps(marker_choices(), ensure_ascii=False, allow_nan=False)
    )
    reply = group_backward_page_worker.request(
        f"preview-group-backward/page/{scenario}",
        {
            "protocol": "group-backward",
            "input": {
                "scenario": scenario,
                "page": "structural",
                "choices": choices,
            },
        },
        timeout=30.0,
    )
    assert reply["output"] == f"PASS group backward {scenario}"
    assert reply["cleanup"] == ZERO_CLEANUP
    _record_group_worker(request, group_backward_page_worker, reply)
```

The marker conversion replaces this exact complete baseline function body:

```python
def test_marker_page_ownership(tmp_path, scenario):
    tree = PageTree()
    tree.feed((ROOT / "wingman/web/index.html").read_text(encoding="utf-8"))
    data = tmp_path / "markers.json"
    data.write_text(
        json.dumps(
            {"page": tree.root, "choices": marker_choices(), "scenario": scenario}
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "node",
            str(ROOT / "tests/fixtures/preview_labelmarkers.cjs"),
            str(data),
            str(ROOT / "wingman/web"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS marker page {scenario}" in result.stdout
```

Replace it exactly with:

```python
def test_marker_page_ownership(labelmarkers_page_worker, request, scenario):
    choices = json.loads(
        json.dumps(marker_choices(), ensure_ascii=False, allow_nan=False)
    )
    reply = labelmarkers_page_worker.request(
        f"preview-label-markers/page/{scenario}",
        {
            "protocol": "label-markers",
            "input": {
                "scenario": scenario,
                "page": "structural",
                "choices": choices,
            },
        },
        timeout=30.0,
    )
    assert reply["output"] == f"PASS marker page {scenario}"
    assert reply["cleanup"] == ZERO_CLEANUP
    _record_labelmarkers_worker(request, labelmarkers_page_worker, reply)
```

The primitive page selectors are replaced by fresh VM-side manifest decodes.
`marker_choices()` remains scenario-request input and is round-tripped through
strict finite JSON before each request, preserving the production expectation
payload without mutable aliases. The final group and marker functions perform no
per-row `Path` construction, `read_text`, `write_text`, file allocation, or Node
subprocess and have no `tmp_path` or `monkeypatch` fixture/name.

Extend the AST/source gate with the two exact permitted signature changes from
the table. For each final function require unchanged decorator AST and reject the
names `tmp_path`, `monkeypatch`, `Path`, `PageTree`, and `subprocess`; reject calls
whose attribute is `read_text`, `write_text`, or `run`. Require exactly one
family worker `.request`, exact protocol/label/timeout/output, the `scenario`,
`page`, and detached `choices` payload keys, zero cleanup, and one property
recording call. Fleet's gate instead requires exact
`(tmp_path, fleetsharing_page_worker, request, scenario)`, retains all
setup/finally state inputs, and rejects only its removed page-file/subprocess
tail.

Collect 205 and require no ID/order change. Before adding CJS completion exports,
run one representative per new family. The Python request path and payload must
reach real source evaluation; RED is the family program's missing completion
export at its call-phase sentinel, never collection/setup failure or removed file
scaffolding. This preserves the completion-export seam for Task 4 Step 2.

- [ ] **Step 2: Convert the three CJS files to dual-entry completion**

Use the same `scenarioCompletion` pattern as Task 3. In Fleet Sharing, set
`const scenarioCompletion = run()` and export/attach catch based on
`require.main === module`; replace the early control-setup terminal at line 809
with a return that still results in exactly one direct `PASS <scenario>` line.
In group backward, preserve both terminal sites, including the early
`focus-fixture-unhydrated` path. Do not change any of the 144 dialog-loop
combinations:

```text
focus-own-dialog:     2 operations × 2 orders × 3 outcomes × 1 owner  = 12
focus-dialog-owners:  2 operations × 2 orders × 3 outcomes × 11 owners = 132
total inner cases = 144
```

Label markers retains every hydration/receipt/reset/capture branch. No assertion
is rewritten as a worker assertion.

- [ ] **Step 3: Pin family-specific diagnostics and adapters**

The worker adapters inject startup page text and preserve current specialized
DOM behavior. Fleet Sharing's in-program `errors` capture becomes the common
VM-local diagnostics collector. Assert:

```text
reject: one error, prefix "bridge: fleet_sharing_watch failed", message "controlled bridge failure"
bridge-source-rejection: two errors in Start then Stop order, exact method prefixes and controlled messages
all other Fleet Sharing cases: zero controlled bridge errors
saved dev: 21 ordered log diagnostics and one theme error diagnostic
business output: exact PASS terminal only, no trailing newline, no duplicate PASS diagnostic
group dev: five ordered log diagnostics; one generated ID equal in appearances 2, 3, and 5
```

Expected product rejection/error scenarios remain `ok:true`. A test assertion or
adapter semantic failure is `ok:false`, not a fatal protocol exit.

- [ ] **Step 4: Switch all four realm qualifications to real programs**

Update only the internal qualification request mode, not test IDs. The exact
representatives are saved `saved-main/reversed`, sharing
`fleet-sharing/missing-worker`, group `group-backward/dev`, and marker
`label-markers/hydration`. Every A-poison-A request executes source text and
production scripts anew. Require one PID per row and no host/realm/input/result/
module/diagnostic/cached-execution poison.

- [ ] **Step 5: Run all 165 and all 205 with exact JUnit evidence**

Run the exact 165 list in collected order, then all four complete files. Require:

```text
165/165 passed; starts 4; request counts 62/65/17/21; one PID each
205/205 passed; all existing ordered IDs/hash exact
165 direct fsync 14 + receipt 19 = 33
205 direct fsync 43 + receipt 19 = 62
no restart, retry, protocol error, late exit, nonzero cleanup, or unexpected diagnostic
```

The non-Node Fleet capacity helper and 39 group Python/API rows remain direct and
account for the unchanged 29-fsync difference.

- [ ] **Step 6: Run normal/reverse/shuffle/cross-family/repeat qualification**

Generate exact lists from the frozen 165 mapping:

```python
normal = node_ids
reverse = list(reversed(node_ids))
shuffle = node_ids.copy()
random.Random(20260926).shuffle(shuffle)
round_robin_families = (
    "fleet-sharing",
    "group-backward",
    "label-markers",
    "saved-layouts",
)
queues = {family: collections.deque(ids) for family, ids in by_family.items()}
cross_family = []
while any(queues.values()):
    for family in round_robin_families:
        if queues[family]:
            cross_family.append(queues[family].popleft())
write_ids_file(Path("/tmp/stage-b-orders/cross-family.ids.txt"), cross_family)
cross_family_bytes = Path("/tmp/stage-b-orders/cross-family.ids.txt").read_bytes()
assert hashlib.sha256(cross_family_bytes).hexdigest() == (
    "183ba77428ec2e3307d1b68716d3427aa75926fbcd1fbcc4b28682d0162131e1"
)
```

The generator writes and validates
`normal.ids.txt`, `reverse.ids.txt`, `shuffle-20260926.ids.txt`, and
`cross-family.ids.txt` with one final newline, reads each back, computes SHA-256
only from those exact ID-only bytes, loads pytest argv only through `load_ids`,
and refuses to invoke pytest if any count, blank/duplicate ID, uniqueness, set
equality, family-prefix first cycle, or frozen hash self-check differs. The
round-robin first cycle is exactly Fleet Sharing,
group-backward, label-markers, saved-layouts; do not rotate it while retaining
the old hash literal.

For each list require exact set/uniqueness, 165 passes, four starts, one PID per
family, exact request counts/ordinals, 33 fsyncs, zero cleanup, and one receipt.
Freeze final-newline hashes: collected remains
`60a253410671d0ac475c414940f007943ff96f4faebc30f0f1aaef9009e549fc`;
reverse remains
`2dff54f5b75dcc262527eedb319b5bf6a7d3def17dae212261b0696529caa718`;
seed shuffle remains
`44823cd4ec00d5e92da597845ac3c2e16b8de6c0edf3cac521b7dc4605fbe39c`;
cross-family remains
`183ba77428ec2e3307d1b68716d3427aa75926fbcd1fbcc4b28682d0162131e1`.

Run each family alone, representative single IDs in fresh processes, repeated
identical requests, and per-family A-B-A. Direct test selection of a module must
still retain its session fixture until pytest session teardown after later
cross-module IDs re-enter it.

- [ ] **Step 7: Run per-family isolation, fatal-request, and business mutations**

Load the same immutable registry and execute `TASK4_RECIPES` in its declared
order. Do not restate or alias a Task 3 recipe: group source re-execution,
business-failure retention, fatal no-replay, the four independent fatal variants,
and the exact 165 inventory each have one canonical Task 4 name. Require
`validate_registry(worktree, BASELINE_COLLECTED_IDS, phase="task4",
scratch_root=prepare_scratch_root("task4"))` before execution and one result per
canonical name afterward.

The external fatal recipes launch and close only the processes in their
`ExternalProbe.mutated` commands, compare exact exit/stdout/stderr and sentinel
stream without JUnit, record those starts as mutation overhead, restore, and run
their exact `ExternalProbe.restored` commands. They never run inside the permanent
cleanup-failure identity and never claim that their starts are part of that
identity's exact value `3`. Pytest IDs/restored companions and any synthetic
callable expectations are read only from their typed registry probe; no owner
shorthand, local regex, or external label passed as a pytest ID is allowed.

- [ ] **Step 8: Commit the independently green four-family conversion**

```bash
node --check tests/fixtures/page_scenario_worker.cjs
node --check tests/fixtures/fleetsharing_page.cjs
node --check tests/fixtures/preview_group_backward.cjs
node --check tests/fixtures/preview_labelmarkers.cjs
uv run --no-sync python -m pytest \
  tests/test_preview_savedlayouts_page.py \
  tests/test_fleetsharing_hydration.py \
  tests/test_preview_group_backward.py \
  tests/test_preview_labelmarkers_page.py \
  tests/test_node_scenario_worker.py \
  tests/test_persistent_page_workers.py \
  -q -rs --junitxml=/tmp/stage-b-task4-225.xml
uv run --extra dev ruff check tests/test_preview_savedlayouts_page.py tests/test_fleetsharing_hydration.py tests/test_preview_group_backward.py tests/test_preview_labelmarkers_page.py tests/test_persistent_page_workers.py tests/node_scenario_worker.py tests/test_node_scenario_worker.py
uv run --extra dev ruff format --check tests/test_preview_savedlayouts_page.py tests/test_fleetsharing_hydration.py tests/test_preview_group_backward.py tests/test_preview_labelmarkers_page.py tests/test_persistent_page_workers.py tests/node_scenario_worker.py tests/test_node_scenario_worker.py
git diff --check
git add tests/test_fleetsharing_hydration.py tests/test_preview_group_backward.py tests/test_preview_labelmarkers_page.py tests/fixtures/fleetsharing_page.cjs tests/fixtures/preview_group_backward.cjs tests/fixtures/preview_labelmarkers.cjs tests/test_persistent_page_workers.py docs/ci-persistent-page-workers-stage-b-results.md
git diff --cached --name-only
git commit -m "test: reuse remaining page workers"
```

Expected: exact relevant `225 passed`, with no skips and no existing ID change.

---

### Task 5: Complete Local Endpoint, Mutation Qualification, and Results

**Files:**
- Modify only as a correction requires within the exact 17-path allowlist
- Modify: `docs/ci-persistent-page-workers-stage-b-results.md`
- Materialize outside repository: `/tmp/stage-b-final/**`

**Interfaces:**
- Consumes: green Tasks 1–4, exact baseline artifacts, complete mutation matrix,
  and release-codec prerequisites.
- Produces: final local 16,617 outcome, exact 225 relevant result, authoritative
  local property audit, candidate hashes, protected hashes, and complete results
  ledger.

- [ ] **Step 1: Materialize the final identity/JUnit/property auditor**

Create `/tmp/stage-b-final/audit.py`. Reuse the Task 1 longest-module-prefix
parser. Preserve property elements as a list, never a dictionary:

```python
def properties(case):
    parent = case.find("properties")
    return [] if parent is None else [
        (item.get("name", ""), item.get("value", ""))
        for item in parent.findall("property")
    ]


def unique_property(case, owner, name):
    matches = [value for key, value in properties(case) if key == name]
    assert len(matches) == 1, "stage_b property cardinality"
    return matches[0]
```

Before arithmetic, reject every missing key, duplicate key, unexpected owner,
and unexpected extra `stage_b.*` key. Require the exact ownership/value table at
the top of this plan. Group target rows by family and require one PID and exact
ordinal sets. Load exact frozen ID sets only from validated `.ids.txt` files,
sum direct fsync over those sets, then add the one receipt value. Keep
qualification properties and starts out of those sums; marker/signature checks
read only the paired structured collection reports.

- [ ] **Step 2: Run all 225 implementation-relevant identities**

```bash
FINAL_RELEVANT_REPORT=/tmp/stage-b-final/relevant-225.collection.json
FINAL_RELEVANT_IDS=/tmp/stage-b-final/relevant-225.ids.txt
PYTHONPATH=/tmp/stage-b-baseline \
  STAGE_B_COLLECTION_REPORT="$FINAL_RELEVANT_REPORT" \
  uv run --no-sync python -m pytest \
  tests/test_preview_savedlayouts_page.py \
  tests/test_fleetsharing_hydration.py \
  tests/test_preview_group_backward.py \
  tests/test_preview_labelmarkers_page.py \
  tests/test_node_scenario_worker.py \
  tests/test_persistent_page_workers.py \
  --collect-only -q -p no:cacheprovider -p collect
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  ids-from-collection "$FINAL_RELEVANT_REPORT" "$FINAL_RELEVANT_IDS"
source /tmp/stage-b-baseline/ids.sh
load_ids "$FINAL_RELEVANT_IDS" RELEVANT_NODEIDS
uv run --no-sync python -m pytest "${RELEVANT_NODEIDS[@]}" \
  -q -rs --junitxml=/tmp/stage-b-final/relevant-225.xml
```

Require exactly 225 unique passed outcomes: 205 existing + 13 helper + seven
qualification. Independently assert baseline `217 + 8 = 225`; do not misstate
`205 + 8` as 225 without the helper baseline. Use
`relevant-225.collection.json` for marker/signature/owner audits and raw JUnit
for outcomes/properties; require JUnit node IDs to equal the derived ID file in
order. Require the derived `relevant-225.ids.txt` bytes to equal the frozen actual Task 2
`task2-relevant-225.ids.txt` byte-for-byte, including every module-local
insertion; then compare its ID-file hash with `task2-identity-gate.json`.
Set/subsequence agreement alone is insufficient.

- [ ] **Step 3: Run the complete restoration-safe mutation matrix**

Use the complete, compiled, Ruff-clean Task 1 registry and runner unchanged.
First audit all 71 recipes as one immutable set, compare its SHA-256 with the
Task 1 registry manifest, and require exactly 14 Task 3 plus 16 Task 4 result
records with no missing, duplicate, or extra canonical name. Then call
`validate_registry(worktree, BASELINE_COLLECTED_IDS, phase="task5",
scratch_root=prepare_scratch_root("task5"))` and execute `TASK5_RECIPES` in its
declared order. This task references recipe names only
through that tuple; it
must not reconstruct a defect, owner, sentinel, regex, edit, or probe locally.

For each Task 5 recipe, `run_recipe()` dispatches by the immutable probe kind:

- `pytest` requires exact selected testcase IDs, intended call-phase JUnit
  failure, traceback, one matching assertion-message line, and the exact
  restored pytest IDs passing;
- `external` requires its exact command, exit, byte-exact stdout/stderr and
  sentinel stream, then the exact restored command/exit/stdout/stderr, with no
  pytest-ID, phase, traceback, or JUnit requirement; and
- `synthetic` requires its exact registered in-process callable and exact JSON
  result or exception class/message for mutated and restored calls, with no
  command or JUnit requirement.

All three paths require kind-appropriate forbidden-masking rejection, at least
one literal match-once edit, rejection of every other sentinel, and exact
bytes/SHA-256/binary-diff/NUL-status restoration before the restored probe.
Afterward, read the completed Task 3/4/5 result records for
`REPRESENTATIVE_EVIDENCE_RECIPES` and require seven actual defect executions:
their real registry edits/probes, typed owner IDs or labels, canonical sentinels,
kind-specific evidence fields, restoration, restored checks, and zero cross-
matches. This is the bounded representative execution report; the complete
matrix remains all 71 canonical recipes.

The canonical synthetic `junit-property-cardinality` recipe runs missing and
duplicate-identical property variants internally; both in-process callable
outcomes must produce exact `stage_b property cardinality`, with no fabricated
pytest phase. There is no second property recipe or phase reference. The
canonical synthetic `restoration-byte-integrity` callable likewise owns exact
`restoration bytes mismatch` and its restored callable result.

The `late-rejection-attribution` probe additionally checks `.scenario == T`,
prior `S`, request `N`, and exact `before the next request`. Its restored argv
also runs the unchanged helper wait-discovery ID with exact
`before replying to the next request`, plus the broken-write and close phase
witnesses. The four fatal variants remain Task 4 registry results with separately
reported overhead and cannot inflate the permanent cleanup-failure property's
exact three starts.

- [ ] **Step 4: Run direct CLI, syntax, DOM, and previous-worker gates**

```bash
for file in \
  tests/fixtures/page_scenario_worker.cjs \
  tests/fixtures/preview_savedlayouts.cjs \
  tests/fixtures/preview_capture_sessions.cjs \
  tests/fixtures/preview_dev_capture.cjs \
  tests/fixtures/fleetsharing_page.cjs \
  tests/fixtures/preview_group_backward.cjs \
  tests/fixtures/preview_labelmarkers.cjs \
  tests/fixtures/screenshot_dom.cjs \
  tests/fixtures/screenshot_pages.cjs \
  tests/fixtures/current_screenshot_pages.cjs; do node --check "$file"; done
node --test tests/fixtures/screenshot_dom.test.cjs
node scripts/js_smoke.js
uv run --no-sync python -m pytest \
  tests/test_node_scenario_worker.py \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  tests/test_fittings_page.py \
  tests/test_ui_setup_page.py \
  tests/test_formations_page.py \
  -q -rs
```

Run the cleanup-success direct six-CLI matrix again and compare every stream to
Task 1's frozen representative records. Search for direct CJS callers and require
that the six original scripts remain executable paths; worker mode reads source
text and does not become their CLI.

- [ ] **Step 5: Build/install the release codec and run the complete suite**

```bash
uv sync --locked --extra dev
node --version
cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available(), 'Native integration tests require the built codec'"
FINAL_COMPLETE_REPORT=/tmp/stage-b-final/full-16617.collection.json
FINAL_COMPLETE_IDS=/tmp/stage-b-final/full-16617.ids.txt
PYTHONPATH=/tmp/stage-b-baseline \
  STAGE_B_COLLECTION_REPORT="$FINAL_COMPLETE_REPORT" \
  uv run --no-sync python -m pytest tests/ \
  --collect-only -q -p no:cacheprovider -p collect
uv run --no-sync python /tmp/stage-b-baseline/collect.py \
  ids-from-collection "$FINAL_COMPLETE_REPORT" "$FINAL_COMPLETE_IDS"
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/stage-b-final/full-16617.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/stage-b-final/full-16617.xml /tmp/stage-b-final/full-16617.json
```

Require exactly `16,603 passed + 14 skipped`, zero failures/errors, and 16,617
unique IDs. Use `full-16617.collection.json` for marker/signature/owner audits and
raw JUnit for outcomes/skips/properties; require JUnit node IDs to equal the
derived ID file in order. Require the derived `full-16617.ids.txt` bytes to equal
the frozen actual Task 2 `task2-complete-16617.ids.txt` byte-for-byte;
then require its hash to equal `task2-identity-gate.json`. The accepted 16,609
subsequence and exact eight additions are supporting diagnostics, not a substitute
for this full-order comparison. Require normalized Linux skip array equality to
accepted Stage A and no Node/codec/target/qualification/unexpected native skip.

- [ ] **Step 6: Run Cargo, smoke, global static, formatting, and docs gates**

```bash
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
node scripts/js_smoke.js
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --no-sync python -m pytest tests/test_documentation.py -q
git diff --check 203d2068..HEAD
```

Compile and Ruff-check every `/tmp/stage-b-baseline` and `/tmp/stage-b-final`
Python script. Syntax-check every temporary CJS probe. No generated XML/JSON/list,
archive, cache, wrapper, or mutation file may be tracked.

- [ ] **Step 7: Audit exact 17-path scope, protected hashes, signatures, and leftovers**

Require exact range equality with the 17-path set in this plan. Require no diff
under production/web/workflow/dependency/configuration/packaging paths. Recompute
these protected hashes:

```text
730298e68701348ce175d4db3fd75ac95c343b939d07052e0ea3d772a17615ce  wingman/ui/api.py
a749e6e87bca62bb4d2f07d87bdfbf4cbc4f1f270a39bbabc055e7767b6c13b8  wingman/settings.py
0d19c21c9112cc32eea97ce21c7d021e9f64ec63f0a88d68891e22b02ee798d3  wingman/atomicio.py
e12dc752612c50d373343d223416a78601217a82258495ea0a2b03a8558ceb77  wingman/paths.py
fc0ac1b9f38cc6b4dade3011a57e42b71fdf4bbce9ee6df8d194e0f589d03581  wingman/preview/savedlayouts.py
729bed89e4c17e338237dcd12b345e60048255356efcf331659cf577823dde80  wingman/preview/layoutcontroller.py
1ac13bb6319493c42563fd291c9123fe20d7ba2cdbd7b39f35143225f1dbe118  wingman/preview/layout.py
c25e99234bb1e9856d8aa2d8c6cb910f1b68a55eb0c0a528508ab4a7c4eb5a8d  tests/fixtures/screenshot_dom.cjs
8954cb59cf7c352e8715d3e3f628f1809663f09d48af5401e8d91152e825ca3f  tests/fixtures/current_screenshot_pages.cjs
3ab46cb75d3dfa17fceabab9936dd1ecf8b534e0790acd5e98af73c7207fae6c  tests/fixtures/screenshot_pages.cjs
9524b760b9f74c09b39c7d096cf1e1494b16e6607e8a5c7422d97e9ee4811222  .github/workflows/ci.yml
33620c99049ad82b1366b2c63cf9957ebb9ea928e08445b9ea8fefd28c789412  pyproject.toml
ebf5e1a5e892dd6488385d117c64a14dd0b0575ef9dbc4565b07a3012f9ad499  uv.lock
c6668b09f3fd3aaff0af1ca3a7dbaa77a40d7c349b06c2f42038134e094fa101  packaging/settings-codec/Cargo.toml
2bff46eccefe8c4b1528e646ea6f42ff7d5f732b44f17a3859588f98534a5f71  tests/conftest.py
```

The AST gate permits exactly the six signature substitutions listed above and
no decorator/marker/parameter change. Search changed paths for unfinished-marker
comments, disabled assertions, broad catches without why-comments, fallback
skips, debug prints, unbounded diagnostics, mutable cross-request state,
`require()`/cache eviction of targets, dead one-shot branches, and Stage C work.

- [ ] **Step 8: Finish local results and commit**

Record literal RED/GREEN, order, mutation, JUnit property, receipt, fsync,
worker-start, CLI, diagnostic, complete-suite, skip, hash, scope, and restoration
outputs. Include:

```text
LOCAL CONCLUSION: Stage B preserves all 205 existing target identities and all 12 existing helper identities, adds exactly eight approved identities, serves the healthy 165 Node-owning rows through four family processes, and reduces measured production-case persistence from 1,059 to 33 fsyncs for those rows and from 1,088 to 62 fsyncs for all 205 rows. Qualification overhead is reported separately. Timing values are observations only and establish no speedup or critical-path effect.
```

Then:

```bash
git add docs/ci-persistent-page-workers-stage-b-results.md
git diff --cached --name-only
git commit -m "docs: record persistent page worker verification"
```

---

### Task 6: Polish, Independent Review, Freeze Heads, and Stop Before Publication

**Files:**
- Modify only within the exact 17 paths if review finds a required correction
- Modify: `docs/superpowers/specs/2026-09-26-persistent-page-workers-stage-b-design.md`
- Modify: `docs/superpowers/plans/2026-09-26-persistent-page-workers-stage-b.md`
- Modify: `docs/ci-persistent-page-workers-stage-b-results.md`
- Read later, only after explicit publication authorization: GitHub PR/run/job/log/artifact APIs

**Interfaces:**
- Consumes: fully green Task 5 tree and `/tmp/stage-b-final` evidence.
- Produces: polished executable head, independently reviewed result, evidence-only head, clean tree, publication STOP, and a fully specified later hosted audit.

- [ ] **Step 1: Run `polish-core --fix` and inspect every edit**

Review `203d2068..HEAD`. Accept only high-confidence corrections within the exact
17 paths. Reject source movement, production/workflow/config/dependency changes,
new identities, changed business assertions, new retries, target `require()`,
weaker cleanup, receipt reconstruction, and Stage C consolidation. Inspect the
actual diff after the tool; do not trust a summary.

- [ ] **Step 2: Re-run fresh verification after polish**

Rerun exact 13 helper, seven qualification, 62 saved, 165 Node, 205 target, 225
relevant, all four order lists, A-B-A/repeat/single cases, one-shot matrix, fsync
33/62, property audit, mutation matrix if executable bytes changed, previous
workers, full 16,617 suite, Cargo, JS smoke, global Ruff/format, docs, scope,
hashes, and leftover scans. No retry is used to turn a failed order green.

- [ ] **Step 3: Perform self-review and one independent review**

Self-review against every spec invariant and stop condition. The independent
review must inspect the approved spec, exact `203d2068..HEAD` diff, results,
JUnit/property audit, direct streams, mutation reports, and this checklist. The
current planning request authorizes no subagent; at execution time use an
independent reviewer only with separate authorization, otherwise stop for
maintainer review rather than silently self-certifying.

The reviewer checks strict numeric schema; request/family/protocol validation;
no target imports; fresh VM/DOM/CommonJS/prototype isolation; primitive-only
mailbox/completion; timer/listener/unresolved promise cleanup; before/boundary/
late rejection ownership; fatal-vs-business recovery; exact diagnostics and
one-shot streams; 144 group dialog combinations; one 19-fsync receipt and
restoration; exact IDs/signatures/properties/starts/fsyncs; full skips; and exact
17-path scope.

- [ ] **Step 4: Run `change-explainer` and update reviewer-facing results**

Record what changed, request lifecycle, adapter boundaries, why module-local
session fixtures survive cross-module re-entry, why private test coupling is
bounded, direct CLI behavior, failure semantics, receipt lifetime, mutation
proof, exact verification, deviations, remaining risks, and reviewer focus. Do
not reference local scratch paths in a future PR description.

- [ ] **Step 5: Freeze executable head and commit evidence only**

If review required executable corrections, commit them with a narrowly accurate
message and rerun Step 2. Then freeze:

```bash
FROZEN_EXECUTABLE_HEAD=$(git rev-parse HEAD)
test "${#FROZEN_EXECUTABLE_HEAD}" -eq 40
test -z "$(git status --porcelain=v2 --untracked-files=all)"
```

Update the three authorized documentation artifacts with the exact executable
SHA and final evidence. Stage only changed documentation paths, verify the total
base range remains the exact 17-path set, and commit:

```bash
git add \
  docs/superpowers/specs/2026-09-26-persistent-page-workers-stage-b-design.md \
  docs/superpowers/plans/2026-09-26-persistent-page-workers-stage-b.md \
  docs/ci-persistent-page-workers-stage-b-results.md
git diff --cached --name-only
git diff --cached --check
git commit -m "test: finalize persistent page workers Stage B"
EVIDENCE_HEAD=$(git rev-parse HEAD)
test "${#EVIDENCE_HEAD}" -eq 40
test -z "$(git status --porcelain=v2 --untracked-files=all)"
printf 'FROZEN_EXECUTABLE_HEAD=%s\nEVIDENCE_HEAD=%s\n' "$FROZEN_EXECUTABLE_HEAD" "$EVIDENCE_HEAD"
```

Require every executable path byte-identical between frozen and evidence heads.

- [ ] **Step 6: STOP**

Return frozen/evidence SHAs, exact commits, checks, structural counts, scope,
restoration, and concerns. Do not push, open/update a PR, dispatch/rerun Actions,
or download candidate artifacts. The current request authorizes versioning but
not publication.

- [ ] **Step 7: Only after separate explicit publication authorization, bind remote inputs**

Require literal values; never infer latest:

```bash
REPOSITORY=elboaf/FlyGD-Wingman
: "${FROZEN_EXECUTABLE_HEAD:?required}"
: "${REVIEWED_HEAD:?required}"
: "${PR_NUMBER:?required}"
: "${RUN_ID:?required}"
test "$(git rev-parse HEAD)" = "$REVIEWED_HEAD"
test -z "$(git status --porcelain=v2 --untracked-files=all)"
git log -5 --oneline --decorate
gh pr view "$PR_NUMBER" -R "$REPOSITORY" --json number,state,mergedAt,headRefOid,baseRefOid,headRefName,baseRefName,url
gh api "repos/$REPOSITORY/actions/runs/$RUN_ID"
```

Never amend a merged PR, never use `--no-verify`, and do not rerun an attempt
without recording every prior attempt.

- [ ] **Step 8: Collect logs-primary, rerun-aware hosted evidence**

Materialize `/tmp/stage-b-hosted-$RUN_ID/{api,logs,artifacts,audit}`. Download run
JSON and every attempt JSON, exact jobs and logs per attempt, artifact metadata,
and uniquely selected Ubuntu/Windows ZIPs. Selection requires exact artifact
name, run ID, reviewed head, non-expired state, and creation within the owning job
window.

For checks, Ubuntu, and Windows logs, require exactly one checkout line
`HEAD is now at <synthetic-short> Merge <head40> into <base40>` and the following
full `git log -1 --format=%H`. Fetch those literal SHAs and require:

```python
parents = command("git", "rev-list", "--parents", "-n", "1", synthetic).split()
assert parents == [synthetic, base, reviewed_head]
```

If run `pull_requests` is empty, record it as absent and require explicit current
PR number/head/base corroboration. A failed/cancelled/missing-artifact attempt is
reported, never overwritten by a later retry.

Verify API digest equals downloaded ZIP SHA-256, exact ZIP members are
`pytest-result.xml` and `pytest-timing.json`, and extracted/member bytes match.
Parse raw JUnit directly; the timing summary intentionally omits `stage_b.*` and
is not a property source.

- [ ] **Step 9: Enforce hosted identities, properties, scope, and observations**

Require all jobs success and:

```text
complete IDs: 16,617 unique and byte-for-byte equal to frozen Task 2 full order
accepted 16,609 subsequence: unchanged supporting diagnostic
additions: exact eight IDs in this plan
Ubuntu: 16,603 passed + 14 unchanged skips
Windows: 16,550 passed + 67 unchanged skips
no failure/error or target/qualification/Node/codec/unexpected-native skip
synthetic base diff: exact 17 paths
frozen executable files: byte-identical at reviewed head and synthetic checkout
```

Run the exact property auditor. Require unique owners/keys and values; four
family/PID pairs; ordinals `1..62/65/17/21`; direct sums `14/43`; receipt `19`;
healthy totals `33/62`; qualification starts `1/1/1/1/1/3/0`; qualification
fsyncs `0/0/0/0/4/0/0`; and no extra `stage_b.*` property. Recheck one-shot
diagnostic contracts from tests and exact 17-path protected hashes.

Report per-file target sums, Node-165 sum, complete testcase sum, XML suite time,
pytest CLI elapsed, Test-step time, and job time separately for each platform.
All are observations; do not attribute a difference to Stage B.

- [ ] **Step 10: Classify and stop again**

Use only:

- `PASS`: exact provenance, artifacts, identities, outcomes, skips, properties,
  scope, and hashes pass;
- `INCONCLUSIVE`: missing/incomparable artifact, failed/cancelled unrelated run,
  or unbound provenance;
- `STOP`: identity, skip, property, scope, protected hash, protocol, or cleanup
  contract differs.

If separately authorized, commit only the results evidence update. Do not push
that evidence commit without another explicit authorization covering its SHA.

---

## Plan-Author Disposable Validation

The plan was checked against merged `203d2068` without writing implementation to
the versioned worktree. The pre-existing disposable overlay was inspected first
and was not accepted as final code because it host-required `screenshot_dom.cjs`
and did not integrate the hardened rejection/protocol contract. Its proven
business-program execution was reused only as a source-compatible feasibility
layer; strict schema, source retention, rejection ownership, fatal request, and
late-exit behavior were independently reconstructed as disposable boundary
programs.

Fresh checks performed while authoring this plan:

- the exact four target files plus the existing helper module passed all `217`
  baseline identities: `217 passed in 46.10s`; JUnit SHA-256
  `c2e57fb3ddf10f7b8a44267423d23160d0762b3fd7137cd4cc0d1b50c31d187f`;
- a fresh disposable copy of the proposed helper test against the old validator
  failed in the call phase at exactly `numeric-schema bool-id: invalid reply was
  accepted`; the bool-ID reply contained valid `duration_ms: 0`, so malformed
  JSON, a duration defect, and ID mismatch could not mask RED;
- applying only the planned `_validate_reply` edit to the revised disposable
  helper made all 13 identities pass (`13 passed in 3.62s`); integer `0` and
  float `1.5` were accepted, boolean ID/duration plus negative/NaN/positive-
  infinity/negative-infinity were rejected, every bad process was discarded,
  and every recovery used a distinct PID with a monotonic ID;
- a discard mutant that raised the protocol crash without stopping or clearing
  the child failed at exact call-phase sentinel `numeric-schema bool-id:
  rejected process was not terminated` (`1 failed in 1.77s`), with no preceding
  `wait()`, timeout, or leaked child; restoring the validator immediately made
  the selected helper pass (`1 passed in 0.34s`);
- all seven target sources were read as UTF-8, compiled under explicit VM
  CommonJS wrappers, left zero target cache/child entries, and kept export poison
  in its originating realm; the manifest hashes matched the approved spec;
- rejection-before and timer-boundary ordering plus ignored-record/early-query
  counterexamples passed their disposable assertions;
- the permanent cleanup-failure sequence was replayed disposably as exactly
  three starts: process A died on one missing-`input` representative fatal,
  process B published success then exited late, `T` caused no replacement start,
  and process C recovered; malformed NDJSON, wrong family, unknown protocol, and
  unknown scenario then ran as four independent bad+recovery process pairs,
  producing `PASS permanent starts=3; fatal-variant overhead starts=8` with no
  valid fatal reply;
- malformed startup/schema probes likewise emitted no valid reply and exited,
  while recognized invalid business data returned `ok:false` and retained the
  process;
- a late post-success rejection made the next call fail with prior request
  context and allowed only a following separate request to restart;
- all six direct entrypoints passed representative success, missing-argv, and
  corrupt-input checks with exact terminal/stream roles; saved dev retained 21
  DEV lines plus PASS and its known stderr error, and group dev retained five DEV
  lines plus PASS and empty stderr;
- the real receipt sequence produced 22 values, exactly 19 fsyncs, valid durable
  UTF-8 JSON, restored environment/writer/legacy identities, no retained
  Stage-B-owned reader/object weak reference after GC, 55 independent decodes,
  and 55 passing saved-main requests in one PID; unrelated old weak keys were not
  required to survive;
- the source-compatible four-family overlay passed all 165 business rows in
  normal, reverse, seed-`20260926` shuffle, and cross-family orders; the
  cross-family generator's exact first-cycle order was Fleet Sharing,
  group-backward, label-markers, saved-layouts and its reread final-newline hash
  was `183ba77428ec2e3307d1b68716d3427aa75926fbcd1fbcc4b28682d0162131e1`; every run
  had request counts `62/65/17/21`, one PID per family, successful A-B-A replay,
  and zero reported host timers;
- four representative poison/pristine real-program runs passed in four PIDs;
- measured components reproduce candidate arithmetic `19 + 10 + 4 = 33` and
  `33 + 29 = 62`; the executor still must obtain integrated raw-JUnit evidence
  from the final implementation before claiming acceptance;
- the disposable identity-order checker collected exactly 217 current baseline
  IDs, proved all eight approved planned IDs absent, validated their exact
  module/function/parameter/Task 2 declarations and selected-set equality, then
  rejected typo, unexpectedly-present, undeclared, duplicate, and wrong-owner
  mutants (`PASS baseline=217 planned=8 absent=8 identity-mutants=5`);
- the disposable canonical-registry **schema checker** compiled and passed Ruff
  check/format, loaded the exact 71-name `14/16/41` partition, proved unique
  names/sentinels and zero regex cross-matches, and compared all 71
  `EXPECTED_OWNERS` entries; explicit assertions covered the corrected
  receipt-count, two sharing-diagnostic, two group-matrix, and marker-deferred
  owners, while the three `RESTORED_ONLY_IDS` were separately exact, unique, and
  disjoint from all selected failure owners (`PASS registry-schema=71 owners=71
  phases=71 corrected-owners=6 restored-only=3 cross-matches=0
  generic-restoration=1`);
- its literal-file loop checked only the registry runner's generic match-once and
  restoration mechanics against disposable fixtures. It did **not** contain the
  future Stage B implementation's real old/new bytes or probe commands, did not
  execute real Stage B defects, and is not representative mutation evidence;
  the seven actual representative executions named by
  `REPRESENTATIVE_EVIDENCE_RECIPES`, and the full 71-recipe run, remain future
  Tasks 3–5 evidence;
- the general plan checker found six task headings, exercised valid, missing,
  and duplicate-identical property lists with exact
  `stage_b property cardinality`, regenerated all 165 round-robin IDs and the
  hash above, and rejected stale duplicate mutation tables, aliases, and the
  removed runner forward reference; the helper and fatal-variant disposable
  scripts also compiled, passed Ruff, and their CJS passed `node --check`;
- the repaired plan preflight checker found six tasks and 51 steps, exact
  `14/16/41 = 71` registry order, eight explicit non-pytest label owners, three
  typed dispatcher contracts, seven unique qualification RED sentinels, exact
  collector-before-217-before-registry command order, byte-exact saved-main,
  group, and marker baseline body replacements, literal in-memory reachability
  for all 17 group and 21 marker scenarios, structured-report/ID-only separation,
  frozen Task 2 expected/actual order gates, and zero stale contradictions;
  documentation tests passed separately;
- placeholder/count review found no unresolved implementation value presented as
  fact: candidate full-suite hashes remain explicitly deferred, while IDs,
  outcomes, process/fsync arithmetic, six tasks, literal-recipe requirements,
  and exact 17-path scope are fixed. The final Task 1 and Task 5 scripts still
  require their own fresh compile/Ruff/self-test runs because disposable plan
  probes are not implementation acceptance artifacts.

This evidence qualifies the literal sequence and witnesses, not the future
repository implementation. Tasks 2–6 rerun every relevant check against the
actual 17-path candidate; the prior overlay cannot satisfy or substitute for the
final no-host-require, rejection-boundary, JUnit-property, or integrated fsync
acceptance gates.

## Stop Conditions

Stop and return for explicit design/scope review if any approved-spec stop
condition triggers, especially if:

1. any path outside the exact 17 is required;
2. production/web/workflow/dependency/configuration/packaging or
   `screenshot_dom.cjs` must change;
3. `NodeScenarioWorker` needs more than exact numeric validation;
4. any existing identity, marker, parameter, assertion, internal matrix, timeout,
   direct argv/PASS/stream contract, or ordered hash changes;
5. healthy 165 execution requires other than four family processes;
6. a target must be host-required, cache-evicted, or exposed through a host
   object/function/constructor/promise/error/timer handle;
7. cleanup cannot complete before reply, before/boundary rejection cannot belong
   to the active request, or business failure cannot retain the process;
8. late rejection cannot fail the next call before its business scenario runs
   with the existing new-scenario attribution and exact phase;
9. one detached 19-fsync receipt cannot serve all 55 main rows while restoring
   environment/writer/legacy identities and releasing every Stage-B-owned
   reader/object reference without asserting survival of unrelated weak keys;
10. worker/fsync evidence cannot be uniquely owned in raw JUnit without a print
    fallback;
11. the Task 1 217-collected/8-planned identity declaration or the post-Task-2
    225/16,617 hard collection gate differs;
12. exact local 16,617 outcome or hosted platform outcomes/skips differ;
13. a timing observation is being used as an acceptance threshold or causal
    claim; or
14. Stage C deletion/consolidation becomes entangled.

## Plan Self-Review

- **Six-task structure:** exactly six reviewable tasks exist: baseline; helper and
  runtime foundation; saved family; three remaining families; complete local
  endpoint; polish/review/freeze/publication stop.
- **Spec coverage:** every invariant maps to a task, including exact identity and
  arithmetic, four process ownership, fresh realms, no target imports, strict
  protocol/business split, rejection boundary, diagnostics, direct CLIs, receipt
  durability, JUnit properties, mutation/order checks, complete suite, and hosted
  provenance.
- **Types and names:** fixture names, family names, protocol labels, request keys,
  reply cleanup keys, immutable receipt bytes/provider, typed mutation probes,
  structured `.collection.json` reports, validated `.ids.txt` argument/hash
  files, JUnit keys, non-pytest labels, and added IDs are consistent across tasks.
- **Identity arithmetic and ordering:** baseline `205 + 12 = 217`; additions
  `7 + 1 = 8`; relevant `205 + 7 + 13 = 225`; complete `16,609 + 8 = 16,617`;
  Linux `16,603 + 14 = 16,617`; Windows `16,550 + 67 = 16,617`. Task 1 validates
  the disjoint 217-collected/8-planned domains without requiring future
  collection; Task 2 then hard-gates fresh actual 225 and 16,617 collections
  byte-for-byte against frozen expected orders, owners, and hashes before Task 3;
  Task 5 compares final JUnit orders byte-for-byte with those frozen Task 2 files.
- **Process/fsync arithmetic:** `62 + 65 + 17 + 21 = 165`; candidate saved
  `19 + 10 + 4 = 33`; candidate all `33 + 29 = 62`; baseline saved
  `1,045 + 10 + 4 = 1,059`; baseline all `1,059 + 29 = 1,088`.
- **Mutation registry:** exactly 71 canonical recipes are partitioned once as
  Task 3/4/5 `14/16/41`; names, phases, edit roots, all 71 expected typed owner
  tuples, literal sentinels, anchored regexes, kind-specific masking, literal
  match-once edits, and pytest/external/synthetic probe expectations have one
  owner. Restored-only IDs are validated separately. No later task duplicates a
  regex table or alias, external labels never enter pytest, and property
  cardinality is one synthetic recipe with two internal variants.
- **No placeholders:** expected Task 2 order hashes are derived from frozen
  baseline/declarations and actual Task 2 hashes are frozen only after fresh
  collection; no fabricated candidate hash or timing value appears.
- **Scope:** no product, workflow, dependency, configuration, packaging, or Stage
  C work appears. Current authorization permits versioning but not push/PR/run.
