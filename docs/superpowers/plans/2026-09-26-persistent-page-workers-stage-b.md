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
- One immutable 71-recipe registry is the sole mutation authority. Tasks 3/4/5 reference its canonical names only; each recipe owns phase, exact IDs, one unique literal sentinel and anchored regex, forbidden masking, match-once edits, and mutated/restored probes. The one property-cardinality recipe owns both missing and duplicate-identical variants internally.
- TDD RED must collect the intended IDs and fail in the call phase at its unique assertion. Undefined imports, collection/setup errors, skips, timeouts, or later generic failures do not count as RED.
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
  -> (saved_layout_page_worker, saved_layout_receipt_json, request, scenario)

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
- Materialize outside the repository: `/tmp/stage-b-baseline/collect.py`, `probe_plugin.py`, `hosted.py`, `restore.py`, `test_restore.py`, `mutations.py`, `test_mutations.py`, ID/map/shape JSON, one-shot NDJSON, fsync JSON, JUnit XML, and hash manifests

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

- [ ] **Step 2: Materialize the exact collection/map/signature and restoration/JUnit tooling**

Create `/tmp/stage-b-baseline/collect.py` with these core checks; store complete
records rather than terminal-only counts:

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


def ordered_hash(rows: list[str]) -> str:
    return hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()


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

Before any RED mutation is run in a later task, also create the complete
`/tmp/stage-b-baseline/restore.py`; no later task may invent or patch a runner.
It owns these frozen interfaces:

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


@dataclass(frozen=True)
class LiteralEdit:
    path: Path
    old: bytes
    new: bytes


@dataclass(frozen=True)
class MutationProbe:
    kind: Literal["pytest-junit", "external-process", "synthetic-audit"]
    argv: tuple[str, ...]
    restored_argv: tuple[str, ...]


@dataclass(frozen=True)
class MutationRecipe:
    name: str
    phase: Phase
    selected_ids: tuple[str, ...]
    sentinel: str
    failure_regex: str
    forbidden_masking: tuple[str, ...]
    edits: tuple[LiteralEdit, ...]
    probe: MutationProbe


def git_bytes(worktree: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(worktree), *args])


def validate_recipe(recipe: MutationRecipe, worktree: Path) -> None:
    assert recipe.name
    assert recipe.phase in ("task3", "task4", "task5")
    assert recipe.selected_ids
    assert recipe.sentinel
    compiled = re.compile(recipe.failure_regex)
    assert recipe.failure_regex.startswith(r"\A")
    assert recipe.failure_regex.endswith(r"\Z")
    assert compiled.fullmatch(recipe.sentinel)
    assert recipe.forbidden_masking
    assert recipe.probe.argv and recipe.probe.restored_argv
    assert recipe.edits or recipe.probe.kind == "synthetic-audit"
    for path in {edit.path for edit in recipe.edits}:
        assert not path.is_absolute(), f"{recipe.name}: path was absolute"
        source = (worktree / path).read_bytes()
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
    worktree: Path,
    recipe: MutationRecipe,
    probe: Callable[[], None],
) -> None:
    validate_recipe(recipe, worktree)
    originals = {
        edit.path: (worktree / edit.path).read_bytes() for edit in recipe.edits
    }
    original_hashes = {
        path: hashlib.sha256(content).hexdigest() for path, content in originals.items()
    }
    before_diff = git_bytes(worktree, "diff", "--binary", "HEAD", "--", ".")
    before_status = git_bytes(
        worktree, "status", "--porcelain=v2", "--untracked-files=all", "-z"
    )
    probe_error: BaseException | None = None
    probe_tb: TracebackType | None = None
    restore_error: BaseException | None = None
    try:
        for relative, original in originals.items():
            path = worktree / relative
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
                (worktree / relative).write_bytes(original)
            checks = {
                "file bytes": all(
                    (worktree / path).read_bytes() == original
                    for path, original in originals.items()
                ),
                "SHA-256": all(
                    hashlib.sha256((worktree / path).read_bytes()).hexdigest()
                    == original_hashes[path]
                    for path in originals
                ),
                "binary diff": git_bytes(
                    worktree, "diff", "--binary", "HEAD", "--", "."
                )
                == before_diff,
                "porcelain status": git_bytes(
                    worktree,
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

On top of that exact restoration primitive, `restore.py` must contain:

- longest-existing-module-prefix reconstruction of exact pytest node IDs;
- raw external JUnit parsing that preserves `<property>` elements as a list;
- `run_expected_failure(recipe, command, xml_path)`, which runs a fresh external
  pytest process, requires nonzero exit, exactly the recipe's selected testcases,
  exactly one intended call-phase `<failure>` and no setup/teardown `<error>` or
  `<skipped>`, then requires exactly one extracted assertion-message line to
  full-match `recipe.failure_regex`;
- rejection of `ImportError`, `ModuleNotFoundError`, collection/fixture errors,
  `NodeScenarioTimeout`, timeout text, and every other registered mutation
  sentinel;
- `run_restored_green(recipe, command, xml_path)`, which runs only after the
  `finally` restoration checks and requires the exact node to pass once; and
- `run_recipe()`, which validates the literal old/new recipe before mutation,
  proves the mutated bytes differ, invokes the failure runner, restores exact
  bytes/SHA-256/binary diff/NUL-delimited porcelain in `finally`, then invokes
  the restored GREEN runner. A failure to restore any one of those surfaces
  raises an error containing the exact sentinel `restoration bytes mismatch`.

The runner never parses pytest terminal prose as an outcome and never imports a
test module into its own process. It extracts call-phase assertion-message lines
from raw external JUnit, requires exactly one line to `fullmatch()` the recipe's
anchored regex, and rejects setup/teardown/collection outcomes structurally.
Literal edits are Python `bytes`, not line numbers, ellipses, pseudocode,
search-only descriptions, or regex substitutions.

#### One canonical mutation registry

Task 1 also creates `/tmp/stage-b-baseline/mutations.py` and
`test_mutations.py`. `mutations.py` is the only mutation authority for the rest
of the plan. Each of its exactly **71** `MutationRecipe` objects contains its
literal name, earliest execution phase, exact selected pytest node IDs (or an
exact `external::...` probe ID), literal sentinel, anchored regex, forbidden
masking rules, match-once byte edits, and complete mutated/restored probe argv.
No Task 3/4/5 prose table may restate an owner, sentinel, regex, edit, or probe.
Those tasks invoke only the phase tuples below by recipe name.

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
```

External selected IDs are exact strings under `external::fatal/*`,
`external::inventory/node-165`, `external::saved-main/receipt-count-55`,
`external::junit/property-cardinality`, and `external::runner/restoration`.
Registry construction fails for any other
non-pytest selected ID. The exact phase contract is:

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
    "external::junit/property-cardinality": frozenset({"task5"}),
    "external::runner/restoration": frozenset({"task5"}),
}
```

`test_mutations.py` checks every recipe's selected ID against this map. A
restored argv may include an additional anti-mask ID from the map, but
`selected_ids` contains only the testcases expected in the mutated JUnit result.

Owner assignment is canonical in `REGISTRY`: the six leading Task 3 realm
recipes select `REALM_SAVED_ID`; the seven receipt-contract recipes select
`RECEIPT_ID`; `receipt-once-construction` selects only
`external::saved-main/receipt-count-55`, whose probe runs all 55 main rows and
parses their raw JUnit while its restored argv includes `RECEIPT_ID` and
`SAVED_REVERSED_ID`. Task 4 adapter/source recipes select
the corresponding exact realm constant; business retention and fatal no-replay
select `CLEANUP_FAILURE_ID`; the four fatal variants select their exact
`external::fatal/...` IDs; diagnostics, group matrices, marker deferred, and
inventory select the exact constants above or `external::inventory/node-165`.
Task 5 schema recipes select `NUMERIC_ID` or `MISSING_FIELDS_ID`; realm recipes
select their exact family ID; source retention and cleanup recipes select
`CLEANUP_SUCCESS_ID`; failure/rejection/fatal/late recipes select
`CLEANUP_FAILURE_ID`; and the final two recipes select the exact JUnit and
restoration external IDs. No recipe stores an owner nickname.

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
```

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

The exact masking tuple is stored unchanged on every recipe:

```python
FORBIDDEN_MASKING = (
    r"\bImportError\b",
    r"\bModuleNotFoundError\b",
    r"\bNodeScenarioTimeout\b",
    r"\bDID NOT RAISE\b",
    r"fixture ['\"][^'\"]+['\"] not found",
    r"ERROR collecting",
    r"(?i:\btime(?:d)? out\b|\btimeout\b)",
)
```

The JUnit parser separately requires the intended call phase and rejects
setup/teardown `<error>` elements. No generic failure, timeout, missing exception,
fixture error, or collection failure can satisfy a recipe. `REGISTRY` is a
literal dict in exact `TASK3_RECIPES + TASK4_RECIPES + TASK5_RECIPES` insertion
order; every value is a fully spelled `MutationRecipe(...)`, not a factory output
or later override.

`validate_registry()` is the mandatory preflight:

```python
def validate_registry(worktree: Path, phase: Phase | None = None) -> None:
    references = TASK3_RECIPES + TASK4_RECIPES + TASK5_RECIPES
    assert len(references) == 71
    assert len(set(references)) == 71
    assert tuple(REGISTRY) == references
    assert all(name == recipe.name for name, recipe in REGISTRY.items())
    assert len({recipe.sentinel for recipe in REGISTRY.values()}) == 71

    for recipe in REGISTRY.values():
        assert recipe.phase in ALLOWED_PHASES_BY_ID[recipe.selected_ids[0]]
        assert all(
            selected in ALLOWED_PHASES_BY_ID
            and recipe.phase in ALLOWED_PHASES_BY_ID[selected]
            for selected in recipe.selected_ids
        )
        assert recipe.forbidden_masking == FORBIDDEN_MASKING
        assert re.fullmatch(recipe.failure_regex, recipe.sentinel)
        assert sum(
            bool(re.fullmatch(other.failure_regex, recipe.sentinel))
            for other in REGISTRY.values()
        ) == 1
        assert not any(
            re.search(mask, recipe.sentinel) or re.search(mask, recipe.failure_regex)
            for mask in FORBIDDEN_MASKING
        )
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
            validate_recipe(recipe, worktree)
```

For recipes whose future phase edits are not present yet, Task 1 runs the full
structural/cross-match checks and validates representative disposable literal
edits; the exact-phase `validate_registry()` call is the first operation after
that phase's GREEN implementation and requires every real old literal to match
once before any mutation. This does not permit changing registry metadata after
its Task 1 manifest hash is frozen.

`test_mutations.py` must prove before Task 3:

1. registry keys, `recipe.name`, and the concatenated phase references are the
   same 71-name set, with every reference count exactly one;
2. all names and sentinels are unique, with the property variants contained
   inside their one canonical recipe;
3. every anchored regex full-matches its own sentinel, and no sentinel
   full-matches any other recipe's regex;
4. every exact selected ID exists in the frozen collection or external-ID
   allowlist and permits that recipe's phase;
5. every recipe carries the complete forbidden-masking tuple, an exact probe,
   and either literal match-once edits or the one synthetic property audit;
6. no sentinel or regex contains a placeholder, generic timeout/setup/
   collection text, or `DID NOT RAISE`; and
7. representative numeric-discard, fresh-realm, fatal-protocol, receipt, JUnit
   cardinality, and restoration recipes mutate literal disposable fixtures,
   fail only at their own sentinel in the intended phase, restore, and pass
   cleanly, with zero cross-matches.

Serialize the complete registry deterministically with names, phases, exact IDs,
sentinels, regexes, forbidden rules, edit paths plus old/new byte SHA-256 values,
and probe argv; write `mutation-registry.json` and its SHA-256 beside the Task 1
artifacts. The Python module, JSON manifest, phase tuples, and hash are frozen
together before Task 3. Later tasks may populate result records but may not add,
rename, alias, or locally reconstruct a recipe; an edit that cannot match the
implemented bytes is a stop-and-correct-registry event, not permission for an
ad hoc mutation.

Create `/tmp/stage-b-baseline/test_restore.py` and run both tooling suites now in
a disposable Git repository. They must additionally prove restoration after an
intended probe failure; zero-match and two-match literal rejection; detection of
bytes/hash/diff/status mismatch at exact `restoration bytes mismatch`; exact-node
mismatch rejection; longest-prefix parsing of a real external pass, call
failure, setup error, and parametrized node; property-list preservation;
sentinel mismatch rejection; and restored GREEN parsing. Only after both suites
pass may Task 3 execute a registry recipe.

Add a `pytest_collection_finish` plugin in the same file that writes exact
`item.nodeid` and sorted marker names to the path in
`STAGE_B_COLLECTION_REPORT`. Derive the 165 rows only from the six named test
functions and parameter mapping above; capture capture/dev program selection and
saved-owner labels explicitly. Write:

```text
/tmp/stage-b-baseline/target-205.txt
/tmp/stage-b-baseline/node-165.txt
/tmp/stage-b-baseline/helper-12.txt
/tmp/stage-b-baseline/node-map.json
/tmp/stage-b-baseline/shapes.json
```

Require exact counts `205/165/12`, uniqueness, the two frozen target hashes, and
all four per-family counts `62/65/17/21`. Assert that every scenario, program,
protocol, label, and timeout equals the approved spec, not merely that totals
match.

- [ ] **Step 3: Capture all one-shot launches, streams, and fsync calls**

Create `/tmp/stage-b-baseline/probe_plugin.py`. Save the real functions before
patching, delegate every call, and restore in `pytest_unconfigure`:

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

- [ ] **Step 4: Run and freeze the complete 217-row baseline**

```bash
uv run --no-sync python -m pytest \
  tests/test_preview_savedlayouts_page.py \
  tests/test_fleetsharing_hydration.py \
  tests/test_preview_group_backward.py \
  tests/test_preview_labelmarkers_page.py \
  tests/test_node_scenario_worker.py \
  -q -rs --junitxml=/tmp/stage-b-baseline/baseline-217.xml
```

Expected: exactly `217 passed`, no skip/failure/error, with the 205 target IDs
followed by all 12 helper IDs. Parse JUnit with longest-existing-module-prefix
resolution and store ordered identity/outcome records and SHA-256. Do not infer
node IDs from dotted classnames by unconditional dot replacement.

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
python -m py_compile /tmp/stage-b-baseline/collect.py /tmp/stage-b-baseline/probe_plugin.py /tmp/stage-b-baseline/hosted.py /tmp/stage-b-baseline/restore.py /tmp/stage-b-baseline/test_restore.py /tmp/stage-b-baseline/mutations.py /tmp/stage-b-baseline/test_mutations.py
uv run --no-sync python -m pytest /tmp/stage-b-baseline/test_restore.py /tmp/stage-b-baseline/test_mutations.py -q
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

Add exactly one non-parametrized test:

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
the new ID against the old validator and require the bool-ID RED above. Reject
import/collection/setup error or a failure caused by an absent scenario branch.

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

Use a session path from `tmp_path_factory.mktemp("saved-layout-receipt")`. Capture
`LOCALAPPDATA`, `paths._use_legacy`, `settings._save_locked`, `os.fsync`, and
`set(settings._COMMITTED_PREVIEWS)` before isolation. The outer
`pytest.MonkeyPatch.context()` sets `LOCALAPPDATA`, wraps the exact captured
`os.fsync` and delegates each call, and forces `_use_legacy=False`. The failed
save uses a nested patch context. Validate `settings.paths.settings_file()` bytes
as strict UTF-8 JSON, the committed reader, pending first Apply, persisted final
Apply, exact production IDs/revisions, and 19 calls before shutdown.

In one outer `try/finally`, call `shutdown_previews()` for both APIs when created,
delete bound methods/controllers/readers, call `gc.collect()`, restore
`paths._use_legacy`, exit patches, and then assert all five baselines and reader
keys. Return only the frozen dataclass above; no path, Api, state, reader,
callback, patch, or mutable receipt escapes.

- [ ] **Step 4: Add all seven qualification identities as synthetic-runtime RED**

Create `tests/test_persistent_page_workers.py` with exactly the seven IDs from
this plan. Parametrize only the four realm rows using:

```python
@pytest.mark.parametrize(
    "family",
    ["saved-layouts", "fleet-sharing", "group-backward", "label-markers"],
)
def test_request_realm_is_fresh_and_program_is_reexecuted(
    family, page_worker_factory, qualification_inputs, request
):
```

Do not add a parameter to either cleanup test. Define one module session input
bundle that builds Text, structural, and Sharing page manifests and direct-CLI
representative payloads; it calls `_saved_layout_receipt_once()` rather than
rebuilding the main receipt. Its extra real setup is exactly owner `saved` (3
fsyncs) plus one shared capture input (1 fsync), reported by cleanup-success as
qualification-only `4`. The receipt's 19 calls remain owned by the saved main
`reversed` JUnit properties.

Initially point all four realm rows and both cleanup rows at synthetic modes in
the new worker request input. The tests must already assert final contracts:
A-poison-A same PID, source execution count one per fresh realm, clean host
prototypes, input/result detachment, module-export isolation, zero cleanup,
Error/primitive/hostile getter/Proxy failures, Promise-then poison, timer/listener/
unresolved-promise cleanup, before/boundary rejection ownership, invalid business
retention, fatal protocol no retry, late-rejection phase/recovery, and exact
worker-start evidence. Task 3 switches saved to real execution and Task 4
switches the other three without changing these IDs.

Run collection first and require all seven exact IDs; then run them and require
RED only because `page_scenario_worker.cjs` does not exist. Undefined Python
imports are forbidden.

- [ ] **Step 5: Implement startup validation and the immutable source registry**

Create `tests/fixtures/page_scenario_worker.cjs`. Require only builtins:

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
restored environment/legacy/writer/reader baselines, production ID/revision
continuity, pending first Apply, final persisted Apply, 55 independent decodes,
and no alias after mutating one.

- [ ] **Step 10: Run Task 2 GREEN and commit**

```bash
node --check tests/fixtures/page_scenario_worker.cjs
uv run --no-sync python -m pytest tests/test_node_scenario_worker.py -q -rs
uv run --no-sync python -m pytest tests/test_persistent_page_workers.py -q -rs
uv run --no-sync python -m pytest \
  tests/test_node_scenario_worker.py \
  tests/test_persistent_page_workers.py \
  -q -rs --junitxml=/tmp/stage-b-task2.xml
uv run --extra dev ruff check tests/node_scenario_worker.py tests/test_node_scenario_worker.py tests/test_preview_savedlayouts_page.py tests/test_persistent_page_workers.py
uv run --extra dev ruff format --check tests/node_scenario_worker.py tests/test_node_scenario_worker.py tests/test_preview_savedlayouts_page.py tests/test_persistent_page_workers.py
git diff --check
git add tests/node_scenario_worker.py tests/test_node_scenario_worker.py tests/fixtures/page_scenario_worker.cjs tests/test_persistent_page_workers.py tests/test_preview_savedlayouts_page.py docs/ci-persistent-page-workers-stage-b-results.md
git diff --cached --name-only
git commit -m "test: add persistent page worker foundation"
```

Expected: 13 helper IDs and seven qualification IDs pass; no business family has
been migrated; existing 217 rows remain green. Record synthetic qualification as
staged foundation evidence, not final real-family acceptance.

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
- Consumes: `NodeScenarioWorker`, `page_scenario_worker.cjs`,
  `_saved_layout_receipt_once()`, Text/structural page trees, and protocols
  `saved-main`, `saved-owner`, `saved-capture`, `saved-dev`.
- Produces: `saved_layout_page_worker`, `saved_layout_receipt_json`, 62 worker
  requests, one family PID, and receipt build/fsync JUnit ownership.

- [ ] **Step 1: Add the saved-family fixture substitutions as collectable RED**

Create the manifest and worker fixtures:

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
def saved_layout_receipt_json(tmp_path_factory: pytest.TempPathFactory) -> str:
    return _saved_layout_receipt_once(tmp_path_factory).receipt_json
```

Add the module-local autouse direct-fsync fixture. It captures and delegates the
real `os.fsync`, counts only function-scope calls, and in `finally` appends one
`stage_b.direct_fsync_calls` property. Higher-scoped manifest/receipt setup must
finish before this fixture starts. Add `_record_saved_worker()` to append family,
PID, and reply ID once, plus the two receipt properties only when
`request.node.nodeid` is exact saved-main `reversed`.

Replace only the three subprocess blocks with worker requests. Main is exact:

```python
input_payload = json.loads(saved_layout_receipt_json)
input_payload["scenario"] = scenario
reply = saved_layout_page_worker.request(
    f"preview-saved-layouts/page/{scenario}",
    {"protocol": "saved-main", "input": input_payload},
    timeout=25.0,
)
assert reply["output"] == f"PASS {scenario}"
assert reply["cleanup"] == ZERO_CLEANUP
_record_saved_worker(request, saved_layout_page_worker, reply)
```

Owner passes `source`, `initial`, `marker`, `visible`, and `copied`, expects
`PASS owner-controls`; capture passes `scenario` and real `initial`, selecting
`saved-dev` only for `dev`. Keep owner/capture production setup and assertions.
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

Materialize exact 62-ID normal, reverse, and `random.Random(20260926)` shuffle
lists. Execute each in a fresh pytest process; require 62 passes, one family PID,
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
order. This phase references recipe names only; exact selected IDs, literal
sentinels/anchored regexes, forbidden masking, byte edits, mutated probes, and
restored probes come exclusively from `REGISTRY`. Before the first mutation,
require `validate_registry(worktree, phase="task3")` to match every Task 3 old
literal exactly once. After each recipe, restore bytes/hash/diff/status and run
its registry-owned restored probe; the saved `reversed` anti-mask case is already
part of the relevant `MutationProbe.restored_argv`, not a second prose recipe.
Write one result per canonical name and reject a missing, duplicate, or extra
Task 3 result.

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

Replace only the direct subprocess block:

```python
reply = fleetsharing_page_worker.request(
    f"fleet-sharing/page/{scenario}",
    {
        "protocol": "fleet-sharing",
        "input": {
            "scenario": scenario,
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
```

Group and marker send `scenario` plus current `marker_choices()` and expect their
exact prefixed terminals at `30.0` seconds. Preserve all Python setup/finally
logic, including both Fleet Sharing shutdown assertions. Collect 205 and require
no ID/order change. Run one representative per new family and require RED only at
missing completion export.

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
assert ordered_hash(cross_family) == (
    "183ba77428ec2e3307d1b68716d3427aa75926fbcd1fbcc4b28682d0162131e1"
)
```

The generator script writes each list with one final newline, reads it back,
recomputes its SHA-256 from those exact bytes, and refuses to invoke pytest if
any count, uniqueness, set equality, family-prefix first cycle, or frozen hash
self-check differs. The round-robin first cycle is exactly Fleet Sharing,
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
`validate_registry(worktree, phase="task4")` before execution and one result per
canonical name afterward.

The external fatal recipes launch and close only the processes in their
registry-owned probes, record those starts as mutation overhead, restore, and run
their registry-owned recovery argv. They never run inside the permanent
cleanup-failure identity and never claim that their starts are part of that
identity's exact value `3`. All other selected IDs and restored companions are
read from their `MutationProbe`; no owner shorthand or local regex is allowed.

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
  tests/test_persistent_page_workers.py \
  tests/test_node_scenario_worker.py \
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
ordinal sets. Sum direct fsync only over exact frozen ID sets, then add the one
receipt value. Keep qualification properties and starts out of those sums.

- [ ] **Step 2: Run all 225 implementation-relevant identities**

```bash
uv run --no-sync python -m pytest \
  tests/test_preview_savedlayouts_page.py \
  tests/test_fleetsharing_hydration.py \
  tests/test_preview_group_backward.py \
  tests/test_preview_labelmarkers_page.py \
  tests/test_persistent_page_workers.py \
  tests/test_node_scenario_worker.py \
  -q -rs --junitxml=/tmp/stage-b-final/relevant-225.xml
```

Require exactly 225 unique passed outcomes: 205 existing + seven qualification +
13 helper. Independently assert baseline `217 + 8 = 225`; do not misstate
`205 + 8` as 225 without the helper baseline. Compare all 205 existing ordered
IDs and markers; compare the 12 existing helper IDs; additions are exactly the
eight listed above.

- [ ] **Step 3: Run the complete restoration-safe mutation matrix**

Use the complete, compiled, Ruff-clean Task 1 registry and runner unchanged.
First audit all 71 recipes as one immutable set, compare its SHA-256 with the
Task 1 registry manifest, and require exactly 14 Task 3 plus 16 Task 4 result
records with no missing, duplicate, or extra canonical name. Then call
`validate_registry(worktree, phase="task5")` and execute `TASK5_RECIPES` in its
declared order. This task references recipe names only through that tuple; it
must not reconstruct a defect, owner, sentinel, regex, edit, or probe locally.

For each Task 5 recipe, require its exact selected IDs and intended call phase,
exactly one assertion-message line matching only its own anchored regex, complete
forbidden-masking rejection, literal match-once edits, restoration, and its
registry-owned GREEN probe. The canonical `junit-property-cardinality` recipe
runs missing and duplicate-identical property variants internally and both must
produce exact `stage_b property cardinality`; there is no second property recipe
or second phase reference. The canonical `restoration-byte-integrity` recipe
likewise owns exact `restoration bytes mismatch`.

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
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/stage-b-final/full-16617.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/stage-b-final/full-16617.xml /tmp/stage-b-final/full-16617.json
```

Require exactly `16,603 passed + 14 skipped`, zero failures/errors, 16,617 unique
IDs, the accepted 16,609 IDs as an unchanged ordered subsequence, and exactly the
eight additions. Freeze the candidate full-order final-newline hash now; the spec
intentionally does not invent it. Require normalized Linux skip array equality
to accepted Stage A and no Node/codec/target/qualification/unexpected native
skip.

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
complete IDs: 16,617 unique
existing ordered subsequence: exact accepted 16,609
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
  UTF-8 JSON, restored environment/writer/legacy/reader state, 55 independent
  decodes, and 55 passing saved-main requests in one PID;
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
- the disposable canonical-registry checker compiled and passed Ruff
  check/format, loaded exactly 71 recipes partitioned `14/16/41`, proved 71
  unique names and 71 unique literal sentinels, full-matched every sentinel only
  to its own anchored regex, audited match-once/restoration literals for all 71,
  and ran seven representative mutation variants (numeric discard, saved realm,
  fatal protocol, receipt, both property-cardinality variants, and restoration)
  with zero cross-matches;
- the general plan checker found six task headings, exercised valid, missing,
  and duplicate-identical property lists with exact
  `stage_b property cardinality`, regenerated all 165 round-robin IDs and the
  hash above, and rejected stale duplicate mutation tables, aliases, and the
  removed runner forward reference; the helper and fatal-variant disposable
  scripts also compiled, passed Ruff, and their CJS passed `node --check`;
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
   environment/writer/legacy/readers;
10. worker/fsync evidence cannot be uniquely owned in raw JUnit without a print
    fallback;
11. exact local 16,617 outcome or hosted platform outcomes/skips differ;
12. a timing observation is being used as an acceptance threshold or causal
    claim; or
13. Stage C deletion/consolidation becomes entangled.

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
  reply cleanup keys, receipt dataclass/provider, JUnit keys, and added IDs are
  consistent across tasks.
- **Identity arithmetic:** baseline `205 + 12 = 217`; additions `7 + 1 = 8`;
  relevant `205 + 7 + 13 = 225`; complete `16,609 + 8 = 16,617`; Linux
  `16,603 + 14 = 16,617`; Windows `16,550 + 67 = 16,617`.
- **Process/fsync arithmetic:** `62 + 65 + 17 + 21 = 165`; candidate saved
  `19 + 10 + 4 = 33`; candidate all `33 + 29 = 62`; baseline saved
  `1,045 + 10 + 4 = 1,059`; baseline all `1,059 + 29 = 1,088`.
- **Mutation registry:** exactly 71 canonical recipes are partitioned once as
  Task 3/4/5 `14/16/41`; names, phases, exact selected IDs, literal sentinels,
  anchored regexes, forbidden masking, literal edits, and probes have one owner.
  No later task duplicates a regex table or alias, and property cardinality is
  one recipe with two internal variants.
- **No placeholders:** unknown candidate full-order/JUnit hashes are explicitly
  derived and frozen only after the candidate exists; no fabricated hash or
  timing value appears.
- **Scope:** no product, workflow, dependency, configuration, packaging, or Stage
  C work appears. Current authorization permits versioning but not push/PR/run.
