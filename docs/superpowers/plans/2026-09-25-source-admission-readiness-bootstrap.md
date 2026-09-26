# Fleet Source-Admission Readiness Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed twelve-turn `publication_rig()` bootstrap with bounded semantic readiness while preserving all 120 source-admission identities, real durable/signed seams, six explicit original-phase cases, independent permission-deadline refusals, and retry pin identity.

**Architecture:** Keep the change inside `tests/test_fleetsharing_source_admission.py`: a private helper drives the real worker one turn at a time until accepted catalogue, eligibility, anchor, proof, full fence, and optional watch observations are current, while `original_phase=True` retains the exact twelve-turn path. Qualification uses temporary restoration-safe instrumentation, production guard mutations, and invalid-authority fault probes; permanent code changes no production, workflow, dependency, marker, selector, budget, or shard.

**Tech Stack:** Python 3.11, pytest, stdlib `ast`/`atexit`/`dataclasses`/`fractions`/`hashlib`/`json`/`subprocess`/`xml.etree.ElementTree`, existing Fleet worker/client/state/timing helpers, uv, Ruff, Node.js smoke, Cargo settings codec, Git, GitHub CLI, and GitHub Actions JUnit/timing artifacts.

**Spec:** `docs/superpowers/specs/2026-09-25-source-admission-readiness-bootstrap-design.md`

## Global Constraints

- Source baseline is merged `main` commit `f6e8ecd5b09889e79aa169ce103b2eb9681cec9f` (`Use native Windows memory evidence for Fleet resource probe (#289)`).
- Current hosted reference is PR #289 run `36147950569`, attempt `2`, synthetic merge `8df553b271fbf0027c73f19bc0df0068d6dc139d`, executable head `599940d147960ef8088212df38d3dd86cc028360`, and base `cc48c887ac3a140a2baf87d4bdcc3f6e916c02c9`.
- Preserve exactly 120 ordered source-admission node IDs, their parameter values/IDs, decorators, markers, test names, and test function signatures. The ordered source-admission SHA-256 is `b79e5648f77c4e9af985085209b66a3b306c2ec56635a4b2a7586de21713a488`.
- Preserve the exact complete ordered 16,609-outcome inventory. Its final-newline SHA-256 is `f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100`.
- PR #289 observations are Windows `14.150s` and Ubuntu `2.835s` for the 120 source-admission testcases. These and every later timing are observations only; make no speedup claim.
- Preserve 39 source-admission test families, 119 `publication_rig()` constructions, and the one family with no rig (`test_failed_combat_ack_does_not_gate_already_authorized_shared_read`).
- Baseline structural counts are 1,428 bootstrap turns, 1,469 real bootstrap `s.save()` calls including 119 seed writes, 1,350 bootstrap worker `_save_state` delegations, 1,928 whole-file real `s.save()` calls, and zero post-bootstrap equality loads.
- Candidate structural counts are 682 bootstrap turns, 921 real bootstrap saves, 802 bootstrap worker save delegations, 1,409 whole-file real saves, and 119 fresh equality loads.
- Structural arithmetic is explicit: baseline turns are `119 × 12 = 1,428`; first semantic readiness across all 119 rigs totals 640 turns, 891 real saves including 119 seeds, and 772 worker delegations; retaining twelve turns for the six approved ordinary rigs adds 42 turns, 30 real saves, and 30 delegations, yielding `682/921/802`.
- Readiness categories remain exactly ordinary `105 @ turn 5 / 7 real saves / 6 delegated saves`, capability ACK `4 @ 6 / 9 / 8`, source watch `9 @ 9 / 12 / 11`, and near-expiry session `1 @ 10 / 12 / 11`; each real-save count includes one seed.
- Exactly six pytest identities retain original phase: three `test_original_source_reaches_real_signed_combat_put` rows, `test_new_mailbox_does_not_replace_selected_current_ticket`, `test_cached_permission_deadline_expires_after_signing_without_utc_renewal`, and `test_independent_deadlines_are_checked_after_real_leaf_wait[proof-False]`.
- The first four original-phase identities retain their exact signed bodies and `sampled_at_ms == 1788782405800` assertions.
- `publication_rig()` adds only keyword-only `original_phase=False`; existing positional behavior, `configure` ordering, rights precedence, and `(worker, client, mono)` return shape stay unchanged.
- `_drive_publication_bootstrap()` reads accepted private test authorities only. It never calls `_work()`, scheduler planning methods, `_publication()`, sleeps, a fallback fixed drive, node-ID/call-stack inference, or direct metadata seeding.
- Full fence equality names all `_Fence` fields: `lifecycle`, `identity`, `session`, `participation`, `source`, `automatic`, and `timing`. Do not use `_Fence.__eq__` because `timing` has `compare=False`.
- Common postconditions use a fresh real `s.load(path)` and prove durable equality, `_needs_device is False`, `client.puts == []`, `_last_published == ()`, empty publisher associations, and `_next_stage_at is None`.
- Strengthen only the existing thread/session retry identities. Add one named effect and exact sample/row/effect key-set, cardinality-three, and pin-object assertions; add no witness test.
- `tests/test_fleetsharing_remote_worker.py` and `tests/test_fleetsharing_worker_fix1.py` stay byte-for-byte unchanged. Their baseline SHA-256 values are `d77a1fa8c0919de4cca443f5f823407ce46461fb5104352853a90df9a25205b7` and `cc3dfe364f8754ebb34d7bedfc16a0eee64349391406161e680f08a7be444b25`.
- The three-file selection remains exactly 167 identities. Normal, reverse-file, reverse-node, and deterministic seed-`20260925` shuffle ordered hashes are respectively `7b9e3644793a89952f132df22b1131c699530c41357b0f92fe4f80873faae89d`, `8890f6fe56c31201dfddc19054f51de8e8beb6be06ae94d63d98945e148c3a9b`, `8acc488cd820e8f289dfaf003c2900fa5f4b63f0d52eb9653af8067d4978c809`, and `2c8be0cd05e8cfb3e1ce5fa4f650cc7049dabf1069d2a95af861317911fd0a0a`.
- Every temporary edit captures exact target bytes and SHA-256, `git diff --binary HEAD -- .`, and NUL-delimited `git status --porcelain=v2 --untracked-files=all -z`; restoration must reproduce all four. A restoration mismatch stops the matrix immediately.
- Qualification recipes are classified as production, readiness-fault, bound, or equivalent. Every selected JUnit testcase must independently match its intended boundary and lack its category's forbidden competing-expiry, barrier, thread-timeout, setup, and collection signatures. The exact bounded bootstrap diagnostic is permitted only for intended readiness-fault and bound probes; it is forbidden masking for production mutations.
- Guard deletions that are equivalent under all valid flows are recorded as non-killing review evidence, not forced into compound mutations. Exact-response, broad full-fence, timing-only fence, timing-field comparison, and durable-equality strength comes from explicit fault probes.
- Full local verification requires Node on `PATH` and the built release settings codec installed in `packaging/bin`; Node, codec, or unexpected native-availability skips invalidate complete-suite evidence.
- Exact complete local outcome is `16,595 passed + 14 skipped`; inspect all 14 skips.
- Exact committed tranche scope is four paths, not five:
  - `docs/superpowers/specs/2026-09-25-source-admission-readiness-bootstrap-design.md`
  - `docs/superpowers/plans/2026-09-25-source-admission-readiness-bootstrap.md`
  - `docs/ci-source-admission-readiness-bootstrap-results.md`
  - `tests/test_fleetsharing_source_admission.py`
- No file under `wingman/`, `.github/`, other test modules, shared helpers, `pyproject.toml`, `uv.lock`, packaging configuration, markers, selectors, budgets, or shards may be committed.
- Before any future publication, stop for explicit authorization. This plan itself authorizes no push, PR update, workflow dispatch/rerun, or hosted acceptance claim.

## File Structure and Ownership

### Created

- `docs/ci-source-admission-readiness-bootstrap-results.md` — exact baseline IDs/families/provenance/skips, structural instrumentation, TDD evidence, guard/fault/mutation evidence, order runs, complete local endpoint, hosted comparison, reviews, scope, restoration, and concerns.

### Modified

- `tests/test_fleetsharing_source_admission.py` — `_drive_publication_bootstrap`, keyword-only `original_phase`, six explicit original-phase identities, two independent proof-boundary precondition blocks, and two strengthened retry identities.

### Read/Verified but Unchanged

- `tests/test_fleetsharing_remote_worker.py`
- `tests/test_fleetsharing_worker_fix1.py`
- `tests/test_fleetsharing_worker.py`
- `tests/fleetsharing_timing_helpers.py`
- `wingman/fleetsharing/worker.py`
- `wingman/fleetsharing/timing.py`
- `wingman/fleetsharing/state.py`
- `wingman/fleetsharing/client.py`
- `wingman/fleetsharing/crypto.py`
- `wingman/fleetsharing/scheduling.py`
- `.github/workflows/ci.yml`

## Interfaces Produced

```python
def _drive_publication_bootstrap(
    worker,
    client,
    mono,
    path,
    *,
    original_phase,
):
    """Drive accepted metadata readiness or the exact original twelve-turn phase."""


def publication_rig(
    tmp_path,
    *,
    configure=None,
    original_phase=False,
    **rights,
):
    """Return the unchanged (worker, client, mono) durable signed rig."""
```

`original_phase` is a strict boolean. `False` drives one real turn at a time and stops on the first exact readiness observation within twelve turns. `True` calls `drive(worker, mono, 12)` once before evaluating readiness and common postconditions.

## Review-Risk Decisions

1. **Readiness authority:** accepted objects and full generation fences define readiness; planned work and absence of due work do not.
2. **Durability:** early return is accepted only after a fresh file load equals the worker state; no cached save argument substitutes for disk authority.
3. **Watch ownership:** source-watch rigs require both accepted source and automatic observations and their exact current status projections.
4. **Original phase:** four source call expressions produce exactly six explicit pytest identities; no seventh identity is admitted because its timing changed.
5. **Deadline independence:** proof refusal is qualified only after sample, current/original session, anchor, row, and effect authorities are explicitly admissible.
6. **Retry identity:** immutable source-derived keys and exact pin objects survive thread restart and session reauthentication; an isolated effect-drop mutant must fail both rows.
7. **Qualification quality:** valid-flow guard deletions, invalid-authority faults, and production mutations are reported separately. No timeout or masked refusal counts.
8. **Claim discipline:** the permanent claim is structural turns/saves/loads plus identity preservation. Hosted timings remain observational even if favorable.

## Spec Coverage Matrix

- **Authority, baseline, and excessive fixed bootstrap:** Global Constraints and Blocks A/C freeze merged source, PR #289 provenance, exact identities/timings/skips, and baseline turns/saves.
- **Fixture interface, bounded helper, accepted authority, diagnostics, and common postconditions:** Interfaces Produced and Block B provide the only fixture entry point, twelve-turn bound, exact object/fence/watch predicate, bounded diagnostics, durable load equality, device completion, zero publication, empty associations, and no stage floor.
- **Six original-phase cases, permission independence, and retry origins:** Block B names all six identities, preserves the first four wire timestamps/bodies, proves competing sample/session/anchor/row/effect deadlines, and asserts exact sample/row/effect key and pin identity through thread/session retry.
- **Lifecycle and test strength:** Blocks C/D retain real save/load/fsync, revision-before-client transport, scheduler deadlines/due work, source authorities, pins, threads, barriers, recovery, signing, and original origins; instrumentation never substitutes a fake store.
- **Compatibility and identity contract:** Blocks A/E/F preserve exact 120, 167, and 16,609 inventories, AST decorators/signatures, unchanged caller bytes, normalized skips, and four one-shot order runs.
- **Qualification:** Block D separates equivalent valid-flow guard deletions from invalid-authority faults and production mutations, requires intended assertions, rejects masked/timeout kills, aggregates ordinary failures, and makes restoration failure fatal.
- **Local and hosted verification:** Tasks 4/5 include prerequisites, focused/subsystem/full suites, Node/Cargo/Ruff, scope checks, rerun-aware logs-primary hosted evidence, exact artifact selection, and observational timing only.
- **Data lifecycle, failure behavior, security, compatibility, and observability:** temporary state remains per-test and restored; failures are bounded and diagnostic; no secrets or payload bodies are added to committed evidence; public/production interfaces stay unchanged; structural and timing evidence are kept distinct.
- **Rejected alternatives, risks, stopping rules, exact scope, self-review, and follow-up boundary:** Review-Risk Decisions, Stop Conditions, the four-path scope, and Plan Self-Review Checklist reject fixed-five-turn, cached/pre-seeded, `_work()`-inspection, all-semantic-phase, node-ID/call-stack, production scheduler, fixture caching, test consolidation, workflow-selection, budget, and shard expansion.

## Task Right-Sizing

1. Task 1 freezes the merged `f6e8ecd5`/PR #289 baseline and creates the results ledger with exact identities, families, provenance, skips, and real structural instrumentation.
2. Task 2 performs TDD for the readiness helper, original-phase option, six exact identities, common postconditions, and independent proof-boundary preconditions; then runs readiness faults, one-turn-short probes, orders, and candidate structural instrumentation.
3. Task 3 strengthens the two retry identities and runs all 41 classified qualification recipes—18 production, 5 readiness-fault, 4 bound, and 14 equivalent—with exact restoration, per-ID JUnit assertion checks, and no masked/timeout kills.
4. Task 4 completes the local endpoint: exact identity/order/scope audits, relevant Fleet tests, complete suite, Node/native codec/Cargo/JS/Ruff, restoration, and results.
5. Task 5 runs polish/final review/change explanation, records the pre-publication stop, and only after separate authorization performs a rerun-aware hosted comparison against PR #289 with exact identities/skips and no speedup claim.

---

## Reproducibility Block A — baseline collection and PR #289 artifact audit

Materialize both files exactly in Task 1. The collector extracts `f6e8ecd5` to a disposable directory, collects source/full identities without changing the worktree, freezes AST decorators/signatures for all 39 families, verifies both platform artifacts, reparses logs-primary checkout provenance, accepts the run's empty `pull_requests` metadata only because the explicit PR record corroborates head/base, verifies rerun attempt 2 selection, and emits Markdown appendices containing all 120 and all 16,609 ordered IDs.

```bash
cat > /tmp/source_readiness_collection_plugin.py <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path


def pytest_collection_finish(session):
    rows = [
        {
            "nodeid": item.nodeid,
            "markers": sorted(marker.name for marker in item.iter_markers()),
        }
        for item in session.items
    ]
    Path(os.environ["SOURCE_READINESS_COLLECTION_OUT"]).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
PY
cat > /tmp/source_readiness_baseline.py <<'PY'
from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

W = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-source-admission-readiness")
ART = Path("/tmp/wingman-windows-memory-hosted-36147950569")
OUT = Path("/tmp/wingman-source-readiness-baseline")
BASE = "f6e8ecd5b09889e79aa169ce103b2eb9681cec9f"
TARGET = "tests/test_fleetsharing_source_admission.py"
CALLERS = (
    "tests/test_fleetsharing_remote_worker.py",
    "tests/test_fleetsharing_worker_fix1.py",
)
EXPECTED_TARGET_HASH = (
    "b79e5648f77c4e9af985085209b66a3b306c2ec56635a4b2a7586de21713a488"
)
EXPECTED_COMPLETE_HASH = (
    "f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100"
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def nodes_digest(nodes: list[str]) -> str:
    return digest(("\n".join(nodes) + "\n").encode())


def extract(commit: str, root: Path) -> None:
    raw = subprocess.check_output(["git", "-C", str(W), "archive", commit])
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        archive.extractall(root, filter="data")


def collect(root: Path, args: list[str], output: Path) -> list[dict[str, object]]:
    env = dict(
        os.environ,
        PYTHONPATH=f"{root}:/tmp",
        SOURCE_READINESS_COLLECTION_OUT=str(output),
    )
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *args,
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "source_readiness_collection_plugin",
        ],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(output.read_text(encoding="utf-8"))


def identity(case: ET.Element) -> str:
    parts = case.get("classname", "").split(".")
    assert len(parts) >= 2 and parts[0] == "tests", parts
    return "::".join(("/".join(parts[:2]) + ".py", *parts[2:], case.get("name", "")))


def normalized_skip(text: str) -> str:
    return re.sub(
        r"pytest-of-[^/\s]+/pytest-\d+/[^\s:\"']+",
        "pytest-of-USER/pytest-N/PYTEST_TMP",
        text.replace("\\", "/"),
    )


def source_shape(root: Path) -> list[dict[str, object]]:
    source = (root / TARGET).read_text(encoding="utf-8")
    tree = ast.parse(source)
    rows = []
    for node in tree.body:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and node.name.startswith("test_"):
            rows.append(
                {
                    "name": node.name,
                    "args": [argument.arg for argument in node.args.args],
                    "posonlyargs": [argument.arg for argument in node.args.posonlyargs],
                    "kwonlyargs": [argument.arg for argument in node.args.kwonlyargs],
                    "vararg": node.args.vararg.arg if node.args.vararg else None,
                    "kwarg": node.args.kwarg.arg if node.args.kwarg else None,
                    "decorators": [
                        ast.dump(value, include_attributes=False)
                        for value in node.decorator_list
                    ],
                }
            )
    assert len(rows) == 39
    return rows


def parse_artifact(platform: str) -> dict[str, object]:
    root = ART / "artifacts" / platform
    archive = ART / "artifacts" / f"{platform}.zip"
    xml_path = root / "pytest-result.xml"
    timing_path = root / "pytest-timing.json"
    with zipfile.ZipFile(archive) as package:
        assert set(package.namelist()) == {"pytest-result.xml", "pytest-timing.json"}
        assert package.read("pytest-result.xml") == xml_path.read_bytes()
        assert package.read("pytest-timing.json") == timing_path.read_bytes()
    cases = list(ET.parse(xml_path).getroot().iter("testcase"))
    ids = [identity(case) for case in cases]
    target = [
        (node, case)
        for node, case in zip(ids, cases, strict=True)
        if node.startswith(TARGET + "::")
    ]
    counts: defaultdict[str, int] = defaultdict(int)
    seconds: defaultdict[str, float] = defaultdict(float)
    skips = []
    failures = errors = 0
    for node, case in zip(ids, cases, strict=True):
        file_name = node.split("::", 1)[0]
        counts[file_name] += 1
        seconds[file_name] += float(case.get("time", "0") or 0)
        failures += len(case.findall("failure"))
        errors += len(case.findall("error"))
        skipped = case.find("skipped")
        if skipped is not None:
            skips.append(
                (node, normalized_skip(skipped.get("message") or skipped.text or ""))
            )
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    assert timing["case_count"] == len(ids)
    for file_name, row in timing["files"].items():
        assert row["cases"] == counts[file_name]
        assert abs(row["seconds"] - seconds[file_name]) < 1e-9
    assert failures == errors == 0
    assert len(ids) == len(set(ids)) == 16609
    assert len(target) == 120 and not any(
        case.find("skipped") is not None for _, case in target
    )
    return {
        "ids": ids,
        "target_ids": [node for node, _ in target],
        "target_seconds": sum(float(case.get("time", "0") or 0) for _, case in target),
        "complete_seconds": sum(float(case.get("time", "0") or 0) for case in cases),
        "skips": skips,
        "passed": len(ids) - len(skips),
        "target_slowest": sorted(
            ((node, float(case.get("time", "0") or 0)) for node, case in target),
            key=lambda row: row[1],
            reverse=True,
        )[:20],
        "xml_sha256": digest(xml_path.read_bytes()),
        "timing_sha256": digest(timing_path.read_bytes()),
        "archive_sha256": digest(archive.read_bytes()),
    }


def checkout_evidence(path: Path) -> tuple[str, str, str]:
    lines = path.read_text(errors="replace").splitlines()
    merge_pattern = re.compile(
        r"HEAD is now at (?P<short>[0-9a-f]{7,40}) Merge "
        r"(?P<head>[0-9a-f]{40}) into (?P<base>[0-9a-f]{40})"
    )
    full_pattern = re.compile(r"(?P<sha>[0-9a-f]{40})\s*$")
    merges = [match for line in lines if (match := merge_pattern.search(line))]
    commands = [
        index
        for index, line in enumerate(lines)
        if "[command]" in line and "log -1 --format=%H" in line
    ]
    assert len(merges) == len(commands) == 1, (path, merges, commands)
    full = full_pattern.search(lines[commands[0] + 1])
    assert full
    synthetic = full.group("sha")
    assert synthetic.startswith(merges[0].group("short"))
    return synthetic, merges[0].group("head"), merges[0].group("base")


OUT.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="source-readiness-baseline-") as directory:
    root = Path(directory)
    extract(BASE, root)
    target_rows = collect(root, [TARGET], OUT / "source-target.json")
    complete_rows = collect(root, ["tests"], OUT / "source-complete.json")
    shapes = source_shape(root)
    caller_hashes = {name: digest((root / name).read_bytes()) for name in CALLERS}

target_ids = [str(row["nodeid"]) for row in target_rows]
complete_ids = [str(row["nodeid"]) for row in complete_rows]
assert len(target_ids) == len(set(target_ids)) == 120
assert len(complete_ids) == len(set(complete_ids)) == 16609
assert nodes_digest(target_ids) == EXPECTED_TARGET_HASH
assert nodes_digest(complete_ids) == EXPECTED_COMPLETE_HASH
assert caller_hashes == {
    CALLERS[0]: "d77a1fa8c0919de4cca443f5f823407ce46461fb5104352853a90df9a25205b7",
    CALLERS[1]: "cc3dfe364f8754ebb34d7bedfc16a0eee64349391406161e680f08a7be444b25",
}

platforms = {name: parse_artifact(name) for name in ("ubuntu", "windows")}
for data in platforms.values():
    assert data["ids"] == complete_ids
    assert data["target_ids"] == target_ids
assert platforms["windows"]["target_seconds"] == 14.150000000000002
assert platforms["ubuntu"]["target_seconds"] == 2.8349999999999977
assert (platforms["ubuntu"]["passed"], len(platforms["ubuntu"]["skips"])) == (16595, 14)
assert (platforms["windows"]["passed"], len(platforms["windows"]["skips"])) == (
    16542,
    67,
)

selected = json.loads((ART / "selected.json").read_text(encoding="utf-8"))
assert selected["run_id"] == 36147950569
assert selected["run_attempt"] == 2
assert selected["synthetic_merge"] == "8df553b271fbf0027c73f19bc0df0068d6dc139d"
assert selected["head"] == "599940d147960ef8088212df38d3dd86cc028360"
assert selected["base"] == "cc48c887ac3a140a2baf87d4bdcc3f6e916c02c9"
assert selected["run_pull_request_metadata"] == "absent"
assert selected["current_pr"]["number"] == 289
assert selected["jobs"]["checks"]["id"] == 108120750881
assert selected["jobs"]["ubuntu"]["id"] == 108120706191
assert selected["jobs"]["windows"]["id"] == 108120703895
assert selected["artifacts"]["ubuntu"]["id"] == 10869653565
assert selected["artifacts"]["windows"]["id"] == 10871003945
assert (
    selected["artifacts"]["ubuntu"]["digest"]
    == "sha256:d757b877ad9f300f53629e4b94b1a9d6b8e838ca956ba788d6549bfa2e4513a2"
)
assert (
    selected["artifacts"]["windows"]["digest"]
    == "sha256:efe34b18fc7760b6a41ac211adfbbfacc10abbbcd8aaacf95dc090b6ade97129"
)
assert (
    "sha256:" + platforms["ubuntu"]["archive_sha256"]
    == selected["artifacts"]["ubuntu"]["digest"]
)
assert (
    "sha256:" + platforms["windows"]["archive_sha256"]
    == selected["artifacts"]["windows"]["digest"]
)

log_rows = {
    checkout_evidence(ART / "logs" / name)
    for name in ("checks.log", "ubuntu.log", "windows.log")
}
assert log_rows == {
    (
        selected["synthetic_merge"],
        selected["head"],
        selected["base"],
    )
}

family_counts = Counter(node.split("::", 1)[1].split("[", 1)[0] for node in target_ids)
assert set(family_counts) == {row["name"] for row in shapes}
assert len(family_counts) == 39

summary = {
    "source": {
        "baseline": BASE,
        "target_count": len(target_ids),
        "target_sha256": nodes_digest(target_ids),
        "complete_count": len(complete_ids),
        "complete_sha256": nodes_digest(complete_ids),
        "family_count": len(shapes),
        "family_shapes": shapes,
        "family_cases": dict(family_counts),
        "caller_hashes": caller_hashes,
    },
    "provenance": {
        "run": selected["run_id"],
        "attempt": selected["run_attempt"],
        "synthetic": selected["synthetic_merge"],
        "head": selected["head"],
        "base": selected["base"],
        "run_pull_request_metadata": selected["run_pull_request_metadata"],
        "jobs": {
            role: selected["jobs"][role]["id"]
            for role in ("checks", "ubuntu", "windows")
        },
        "artifacts": {
            role: {
                "id": selected["artifacts"][role]["id"],
                "digest": selected["artifacts"][role]["digest"],
            }
            for role in ("ubuntu", "windows")
        },
    },
    "platforms": {
        name: {
            key: value
            for key, value in data.items()
            if key not in ("ids", "target_ids")
        }
        for name, data in platforms.items()
    },
}
(OUT / "source-120.txt").write_text("\n".join(target_ids) + "\n", encoding="utf-8")
(OUT / "complete-16609.txt").write_text(
    "\n".join(complete_ids) + "\n", encoding="utf-8"
)
(OUT / "source-shape.json").write_text(
    json.dumps(shapes, indent=2) + "\n", encoding="utf-8"
)
for name in ("ubuntu", "windows"):
    (OUT / f"{name}-skips.json").write_text(
        json.dumps(platforms[name]["skips"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
(OUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
appendix = [
    "## Appendix A — exact ordered source-admission identities",
    "",
    "```text",
    *target_ids,
    "```",
    "",
    "## Appendix B — exact ordered complete inventory",
    "",
    "```text",
    *complete_ids,
    "```",
    "",
]
(OUT / "identity-appendices.md").write_text("\n".join(appendix), encoding="utf-8")
print(json.dumps(summary, sort_keys=True))
PY
python -m py_compile /tmp/source_readiness_collection_plugin.py /tmp/source_readiness_baseline.py
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-source-admission-readiness
uv run --no-sync python /tmp/source_readiness_baseline.py
```

Expected endpoint:

- exact source target `120/120`, hash `b79e5648f77c4e9af985085209b66a3b306c2ec56635a4b2a7586de21713a488`;
- exact complete `16609/16609`, hash `f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100`;
- 39 AST family rows with exact decorators/signatures and matching collected family names;
- Ubuntu `16595 passed + 14 skipped`, source sum `2.835s`;
- Windows `16542 passed + 67 skipped`, source sum `14.150s`;
- zero target failures/errors/skips, exact platform/source order equality;
- logs-primary synthetic/head/base agreement, empty run PR metadata recorded as `absent`, explicit PR #289 corroboration, exact jobs/artifacts/digests, and ZIP-member byte equality.

## Reproducibility Block B — exact permanent test-module edits

Use these Ruff-formatted snippets exactly. They were validated against an archived `f6e8ecd5` tree with `py_compile`, Ruff, and all 120 source-admission cases.

### Imports

Add `Fraction`, the shared combat limits, and the actual worker sample-age constant:

```python
from fractions import Fraction

from wingman.combatprofile import LIMITS
from wingman.fleetsharing.worker import MAX_SNAPSHOT_AGE_S, _Obsolete
```

### Readiness helper and fixture

Replace the existing `publication_rig()` definition with:

```python
def _drive_publication_bootstrap(
    worker,
    client,
    mono,
    path,
    *,
    original_phase,
):
    fence_fields = (
        "lifecycle",
        "identity",
        "session",
        "participation",
        "source",
        "automatic",
        "timing",
    )
    watch_requested = worker._watch

    def observe():
        status = worker.status()
        proof = worker._eligibility_proof
        current_fence = worker._fence()
        proof_fence = proof.fence if proof is not None else None
        fence_differences = tuple(
            name
            for name in fence_fields
            if proof_fence is None
            or getattr(proof_fence, name) != getattr(current_fence, name)
        )
        checks = {
            "catalogue": worker._catalogue is not None,
            "eligibility": worker._eligibility is not None,
            "anchor": worker._timing_context._state.anchor is not None,
            "proof": proof is not None,
            "exact_response": proof is not None
            and worker._eligibility is not None
            and proof.response is worker._eligibility,
            "exact_fence": proof_fence is not None and not fence_differences,
            "source_observation": worker._sources is not None,
            "status_source": status.sources is not None,
            "source_identity": worker._sources is not None
            and status.sources is worker._sources,
            "automatic_observation": worker._automatic_observation is not None,
            "status_automatic": status.automatic_status is not None,
            "automatic_identity": worker._automatic_observation is not None
            and status.automatic_status is worker._automatic_observation,
        }
        ready = all(
            checks[name]
            for name in (
                "catalogue",
                "eligibility",
                "anchor",
                "proof",
                "exact_response",
                "exact_fence",
            )
        ) and (
            not watch_requested
            or all(
                checks[name]
                for name in (
                    "source_observation",
                    "status_source",
                    "source_identity",
                    "automatic_observation",
                    "status_automatic",
                    "automatic_identity",
                )
            )
        )
        return {
            "ready": ready,
            "checks": checks,
            "proof_fence": proof_fence,
            "current_fence": current_fence,
            "fence_differences": fence_differences,
            "status": status,
        }

    def fail(turns, observation):
        operations = tuple(call[0] for call in client.calls[-32:])
        pytest.fail(
            "publication bootstrap readiness missed "
            f"after {turns}/12 turns; checks={observation['checks']!r}; "
            f"watch_requested={watch_requested!r}; "
            f"proof_fence={observation['proof_fence']!r}; "
            f"current_fence={observation['current_fence']!r}; "
            f"fence_differences={observation['fence_differences']!r}; "
            f"status={observation['status']!r}; operations={operations!r}"
        )

    if original_phase:
        turns = 12
        drive(worker, mono, turns)
        observation = observe()
        if not observation["ready"]:
            fail(turns, observation)
    else:
        for turns in range(1, 13):
            drive(worker, mono, 1)
            observation = observe()
            if observation["ready"]:
                break
        else:
            fail(turns, observation)

    assert s.load(path) == worker._state, "bootstrap state is not durable"
    assert worker._needs_device is False, "device bootstrap is incomplete"
    assert client.puts == [], "bootstrap accepted a publication"
    assert worker._last_published == (), "bootstrap installed publication state"
    assert worker._timing_context._publisher.associations == {}, (
        "bootstrap allocated publication evidence"
    )
    assert worker._timing_context._next_stage_at is None, (
        "bootstrap allocated a publication stage floor"
    )


def publication_rig(
    tmp_path,
    *,
    configure=None,
    original_phase=False,
    **rights,
):
    if type(original_phase) is not bool:
        raise TypeError("original_phase must be a bool")
    path = tmp_path / "sharing.json"
    s.save(path, PAIRED_STATE)
    mono = [1000.0]
    approved = dict(
        approved_capabilities=COMBAT_CAPS,
        session_approved_capabilities=COMBAT_CAPS,
        acknowledged_capabilities=COMBAT_CAPS,
    )
    approved.update(rights)
    client = PublicationClient(path, replace(DEVICE, **approved))
    worker = _worker(
        client,
        clock=lambda: mono[0],
        utc_clock=lambda: NOW + timedelta(seconds=mono[0] - 1000),
    )
    worker._load_state = lambda: s.load(path)
    worker._save_state = lambda state: s.save(path, state)
    if configure is not None:
        configure(worker, client, mono)
    _drive_publication_bootstrap(
        worker,
        client,
        mono,
        path,
        original_phase=original_phase,
    )
    return worker, client, mono
```

### Six exact original-phase identities

Use these four source expressions, producing exactly six pytest identities:

```python
# Three parameter rows:
worker, client, mono = publication_rig(tmp_path, original_phase=True)

# test_new_mailbox_does_not_replace_selected_current_ticket:
worker, client, mono = publication_rig(tmp_path, original_phase=True)

# test_cached_permission_deadline_expires_after_signing_without_utc_renewal:
worker, client, mono = publication_rig(
    tmp_path, configure=configure, original_phase=True
)

# test_independent_deadlines_are_checked_after_real_leaf_wait:
worker, client, mono = publication_rig(
    tmp_path,
    configure=configure,
    original_phase=boundary == "proof",
)
```

The exact six IDs are:

```text
tests/test_fleetsharing_source_admission.py::test_original_source_reaches_real_signed_combat_put[0-0]
tests/test_fleetsharing_source_admission.py::test_original_source_reaches_real_signed_combat_put[None-0]
tests/test_fleetsharing_source_admission.py::test_original_source_reaches_real_signed_combat_put[7-None]
tests/test_fleetsharing_source_admission.py::test_new_mailbox_does_not_replace_selected_current_ticket
tests/test_fleetsharing_source_admission.py::test_cached_permission_deadline_expires_after_signing_without_utc_renewal
tests/test_fleetsharing_source_admission.py::test_independent_deadlines_are_checked_after_real_leaf_wait[proof-False]
```

### Cached-permission competing-deadline preconditions

Replace the direct `ticket()` selection in `test_cached_permission_deadline_expires_after_signing_without_utc_renewal` with:

```python
source = ticket(mono[0])
work, fence = selected_publication(worker, mono, source)
target = Fraction(1008)
snapshot = source.snapshot
anchor = worker._timing_context._state.anchor
assert snapshot.sampled_at_mono is not None
assert (
    0 <= target - Fraction(snapshot.sampled_at_mono) < Fraction(MAX_SNAPSHOT_AGE_S)
)
assert work.payload.session_deadline > target
assert worker._expires_at > target
assert anchor is not None
assert 0 <= 1000 * (target - anchor.received_at) <= LIMITS["anchor_lifetime_ms"]
for row in snapshot.rows:
    assert row.combat is not None and Fraction(row.combat.expires_at_mono) > target
    assert all(
        Fraction(effect.expires_at_mono) > target
        for effect in row.combat.observations
    )
assert work.payload.member_deadlines == (target,)
```

These assertions run before `crypto.sign_request` changes monotonic time. They prove the original sample, selected/current session, timing anchor, row/effect evidence, and every competing permission input remain admissible while the proof deadline is exactly `1008`.

### Held-leaf proof competing-deadline preconditions

Immediately after selecting `work, fence` in `test_independent_deadlines_are_checked_after_real_leaf_wait`, add:

```python
def assert_proof_boundary_is_independent():
    if boundary != "proof":
        return
    boundary_time = Fraction(target)
    snapshot = source.snapshot
    anchor = worker._timing_context._state.anchor
    assert snapshot.sampled_at_mono is not None
    assert (
        0
        <= boundary_time - Fraction(snapshot.sampled_at_mono)
        < Fraction(MAX_SNAPSHOT_AGE_S)
    )
    assert work.payload.session_deadline > boundary_time
    assert worker._expires_at > boundary_time
    assert anchor is not None
    assert (
        0
        <= 1000 * (boundary_time - anchor.received_at)
        <= LIMITS["anchor_lifetime_ms"]
    )
    for row in snapshot.rows:
        assert row.combat is not None
        assert Fraction(row.combat.expires_at_mono) > boundary_time
        assert all(
            Fraction(effect.expires_at_mono) > boundary_time
            for effect in row.combat.observations
        )
    assert work.payload.member_deadlines == (boundary_time,)


assert_proof_boundary_is_independent()
```

Call `assert_proof_boundary_is_independent()` again inside `with source._lock:` immediately after `leaf.wait(5)` and before setting `mono[0] = target`. This second call does not re-enter production leaves and proves the same competing authorities at the held transition.

### Exact sample/row/effect retry keys and pins

Replace the complete existing retry test, from its decorator through the `finally` block, with this exact Ruff-formatted block. This replacement is intentionally complete: it removes the legacy `assert all(... for pin in original_pins)` that would iterate dict keys after `original_pins` becomes a mapping.

```python
@pytest.mark.parametrize("restart", ["thread", "session"])
def test_original_measurement_retry_retains_wire_origins_across_reauthentication(
    tmp_path, restart
):
    worker, client, mono = publication_rig(tmp_path)
    effect = EffectObservation(
        "POINT", mono[0] + 28, (LIFETIME, 9001), "Retry hunter"
    )
    source = ticket(mono[0], outgoing=7, effects=(effect,))
    snapshot = source.snapshot
    row = snapshot.rows[0]
    activity = row.combat
    assert activity is not None and activity.observation_id is not None
    assert len(activity.observations) == 1
    accepted_effect = activity.observations[0]
    character_id = next(
        character.character_id
        for character in worker._catalogue.characters
        if character.character_name == row.character
    )
    assert snapshot.sampled_at_mono is not None
    sample_key = (
        snapshot.activation_generation,
        Fraction(snapshot.sampled_at_mono),
    )
    row_key = (
        character_id,
        activity.observation_id[0],
        "row",
        activity.observation_id,
    )
    effect_key = (
        character_id,
        accepted_effect.observation_id[0],
        (accepted_effect.kind, accepted_effect.name),
        accepted_effect.observation_id,
    )
    expected_keys = frozenset((sample_key, row_key, effect_key))
    work, fence = selected_publication(worker, mono, source)
    original_session = s.load(client.path).session_id
    client.put_error = (
        (401, "unauthorized") if restart == "session" else (500, "server_error")
    )
    worker._execute(work, fence)
    assert len(client.puts) == 1
    first = client.puts[0]
    context = worker._timing_context
    associations = context._publisher.associations
    assert frozenset(associations) == expected_keys
    assert len(associations) == 3
    original_pins = {
        sample_key: associations[sample_key],
        row_key: associations[row_key],
        effect_key: associations[effect_key],
    }
    original_floor = context._next_stage_at
    client.put_error = None
    if restart == "thread":
        assert worker.stop() and worker.start()
    try:
        for _ in range(60):
            wait, _ = worker._iterate()
            if len(client.puts) > 1 or mono[0] >= source.snapshot.sampled_at_mono + 5:
                break
            mono[0] += wait  # Honor actual owner cadence, not a post-call500ms sleep.
        assert len(client.puts) == 2, worker.status()
        assert client.puts[-1] == first
        assert worker._timing_context is context
        assert context._next_stage_at >= original_floor
        associations = context._publisher.associations
        assert frozenset(associations) == expected_keys
        assert len(associations) == 3
        assert associations[sample_key] is original_pins[sample_key]
        assert associations[row_key] is original_pins[row_key]
        assert associations[effect_key] is original_pins[effect_key]
        if restart == "session":
            assert s.load(client.path).session_id != original_session
        assert worker._latest is source
    finally:
        assert worker.stop()
```

---

## Reproducibility Block C — real structural instrumentation with exact restoration

The instrumentation wraps and delegates the actual `s.save()` and `drive()` functions, wraps the installed worker `_save_state` delegate after fixture construction, counts the seed separately through the real `s.save()` wrapper, and counts only the explicit fresh equality load. It handles the source module's two import names through one `builtins` record. It never replaces the store, suppresses fsync, changes the client, or derives counts from fake call logs.

Create the editor:

```bash
cat > /tmp/source_readiness_instrument_edit.py <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

root = Path(sys.argv[1])
mode = sys.argv[2]
path = root / "tests/test_fleetsharing_source_admission.py"
text = path.read_text(encoding="utf-8")
text = text.replace(
    "import json\n",
    "import atexit\nimport builtins\nimport json\nimport os\n",
    1,
)
text = text.replace(
    "from math import inf, nextafter\n",
    "from math import inf, nextafter\nfrom pathlib import Path\n",
    1,
)
anchor = "COMBAT_CAPS = (p.SHARED_CAPABILITY, p.COMBAT_CAPABILITY)\n_ROW_EVENTS = count(100)\n"
instrument = r"""
if not hasattr(builtins, "_SOURCE_READINESS_EVIDENCE"):
    builtins._SOURCE_READINESS_EVIDENCE = {
        "mode": os.environ["SOURCE_READINESS_MODE"],
        "rigs": [],
        "whole_file_real_saves": 0,
        "active": None,
        "real_save": s.save,
        "registered": False,
    }
_BOOTSTRAP_EVIDENCE = builtins._SOURCE_READINESS_EVIDENCE
_REAL_SAVE = _BOOTSTRAP_EVIDENCE["real_save"]
_REAL_DRIVE = drive


def _instrumented_save(path, state):
    _BOOTSTRAP_EVIDENCE["whole_file_real_saves"] += 1
    active = _BOOTSTRAP_EVIDENCE["active"]
    if active is not None:
        active["real_saves"] += 1
    return _REAL_SAVE(path, state)


def _instrumented_drive(worker, mono, turns=20, snapshot=None):
    active = _BOOTSTRAP_EVIDENCE["active"]
    if active is not None:
        active["turns"] += turns
    return _REAL_DRIVE(worker, mono, turns, snapshot)


def _instrumented_readiness(worker):
    proof = worker._eligibility_proof
    current = worker._fence()
    fields = (
        "lifecycle",
        "identity",
        "session",
        "participation",
        "source",
        "automatic",
        "timing",
    )
    exact_fence = proof is not None and all(
        getattr(proof.fence, name) == getattr(current, name) for name in fields
    )
    status = worker.status()
    ordinary = (
        worker._catalogue is not None
        and worker._eligibility is not None
        and worker._timing_context._state.anchor is not None
        and proof is not None
        and proof.response is worker._eligibility
        and exact_fence
    )
    watched = (
        worker._sources is not None
        and status.sources is not None
        and status.sources is worker._sources
        and worker._automatic_observation is not None
        and status.automatic_status is not None
        and status.automatic_status is worker._automatic_observation
    )
    return ordinary and (not worker._watch or watched)


def _instrumented_category(worker, client):
    if worker._watch:
        return "watch"
    if client.device.session_expires_at == "2026-09-07T12:00:08.000Z":
        return "near_expiry"
    if client.acks:
        return "ack"
    return "ordinary"


def _write_bootstrap_evidence():
    report = {
        key: value
        for key, value in _BOOTSTRAP_EVIDENCE.items()
        if key not in ("active", "real_save", "registered")
    }
    Path(os.environ["SOURCE_READINESS_OUT"]).write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


s.save = _instrumented_save
drive = _instrumented_drive
if not _BOOTSTRAP_EVIDENCE["registered"]:
    atexit.register(_write_bootstrap_evidence)
    _BOOTSTRAP_EVIDENCE["registered"] = True
"""
assert text.count(anchor) == 1
text = text.replace(anchor, anchor + instrument, 1)

entry = """    nodeid = os.environ["PYTEST_CURRENT_TEST"].rsplit(" (", 1)[0]
    evidence = {
        "nodeid": nodeid,
        "family": nodeid.split("::", 1)[1].split("[", 1)[0],
        "original_phase": ORIGINAL_PHASE,
        "turns": 0,
        "real_saves": 0,
        "worker_saves": 0,
        "equality_loads": 0,
        "first_ready_turn": None,
        "first_ready_real_saves": None,
        "first_ready_worker_saves": None,
    }
    _BOOTSTRAP_EVIDENCE["rigs"].append(evidence)
    _BOOTSTRAP_EVIDENCE["active"] = evidence
"""
worker_counter = """    real_worker_save = worker._save_state

    def counted_worker_save(state):
        if _BOOTSTRAP_EVIDENCE["active"] is evidence:
            evidence["worker_saves"] += 1
        return real_worker_save(state)

    worker._save_state = counted_worker_save
"""

if mode == "baseline":
    old = 'def publication_rig(tmp_path, *, configure=None, **rights):\n    path = tmp_path / "sharing.json"\n'
    new = (
        "def publication_rig(tmp_path, *, configure=None, **rights):\n"
        + entry.replace("ORIGINAL_PHASE", "False")
        + '    path = tmp_path / "sharing.json"\n'
    )
    assert text.count(old) == 1
    text = text.replace(old, new)
    old = "    worker._save_state = lambda state: s.save(path, state)\n    if configure is not None:\n"
    new = (
        "    worker._save_state = lambda state: s.save(path, state)\n"
        + worker_counter
        + "    if configure is not None:\n"
    )
    assert text.count(old) == 1
    text = text.replace(old, new)
    old = """    drive(worker, mono, 12)
    assert worker._catalogue is not None and worker._eligibility is not None
    assert worker._timing_context._state.anchor is not None
    return worker, client, mono
"""
    new = """    for _ in range(12):
        drive(worker, mono, 1)
        if evidence["first_ready_turn"] is None and _instrumented_readiness(worker):
            evidence["first_ready_turn"] = evidence["turns"]
            evidence["first_ready_real_saves"] = evidence["real_saves"]
            evidence["first_ready_worker_saves"] = evidence["worker_saves"]
    evidence["category"] = _instrumented_category(worker, client)
    assert worker._catalogue is not None and worker._eligibility is not None
    assert worker._timing_context._state.anchor is not None
    _BOOTSTRAP_EVIDENCE["active"] = None
    return worker, client, mono
"""
    assert text.count(old) == 1
    text = text.replace(old, new)
elif mode == "candidate":
    old = """    if original_phase:
        turns = 12
        drive(worker, mono, turns)
        observation = observe()
        if not observation["ready"]:
            fail(turns, observation)
"""
    new = """    if original_phase:
        turns = 12
        for _ in range(turns):
            drive(worker, mono, 1)
            observation = observe()
            if observation["ready"] and _BOOTSTRAP_EVIDENCE["active"]["first_ready_turn"] is None:
                _BOOTSTRAP_EVIDENCE["active"]["first_ready_turn"] = _BOOTSTRAP_EVIDENCE["active"]["turns"]
                _BOOTSTRAP_EVIDENCE["active"]["first_ready_real_saves"] = _BOOTSTRAP_EVIDENCE["active"]["real_saves"]
                _BOOTSTRAP_EVIDENCE["active"]["first_ready_worker_saves"] = _BOOTSTRAP_EVIDENCE["active"]["worker_saves"]
        if not observation["ready"]:
            fail(turns, observation)
"""
    assert text.count(old) == 1
    text = text.replace(old, new)
    old = """            observation = observe()
            if observation["ready"]:
                break
"""
    new = """            observation = observe()
            if observation["ready"]:
                _BOOTSTRAP_EVIDENCE["active"]["first_ready_turn"] = _BOOTSTRAP_EVIDENCE["active"]["turns"]
                _BOOTSTRAP_EVIDENCE["active"]["first_ready_real_saves"] = _BOOTSTRAP_EVIDENCE["active"]["real_saves"]
                _BOOTSTRAP_EVIDENCE["active"]["first_ready_worker_saves"] = _BOOTSTRAP_EVIDENCE["active"]["worker_saves"]
                break
"""
    assert text.count(old) == 1
    text = text.replace(old, new)
    old = '    assert s.load(path) == worker._state, "bootstrap state is not durable"\n'
    new = '    _BOOTSTRAP_EVIDENCE["active"]["equality_loads"] += 1\n' + old
    assert text.count(old) == 1
    text = text.replace(old, new)
    old = """    if type(original_phase) is not bool:
        raise TypeError("original_phase must be a bool")
    path = tmp_path / "sharing.json"
"""
    new = (
        """    if type(original_phase) is not bool:
        raise TypeError("original_phase must be a bool")
"""
        + entry.replace("ORIGINAL_PHASE", "original_phase")
        + '    path = tmp_path / "sharing.json"\n'
    )
    assert text.count(old) == 1
    text = text.replace(old, new)
    old = "    worker._save_state = lambda state: s.save(path, state)\n    if configure is not None:\n"
    new = (
        "    worker._save_state = lambda state: s.save(path, state)\n"
        + worker_counter
        + "    if configure is not None:\n"
    )
    assert text.count(old) == 1
    text = text.replace(old, new)
    old = """    _drive_publication_bootstrap(
        worker,
        client,
        mono,
        path,
        original_phase=original_phase,
    )
    return worker, client, mono
"""
    new = """    _drive_publication_bootstrap(
        worker,
        client,
        mono,
        path,
        original_phase=original_phase,
    )
    evidence["category"] = _instrumented_category(worker, client)
    _BOOTSTRAP_EVIDENCE["active"] = None
    return worker, client, mono
"""
    assert text.count(old) == 1
    text = text.replace(old, new)
else:
    raise SystemExit(mode)

path.write_text(text, encoding="utf-8")
PY
python -m py_compile /tmp/source_readiness_instrument_edit.py
```

Create the restoration-safe runner:

```bash
cat > /tmp/source_readiness_instrument_run.py <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

W = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-source-admission-readiness")
TARGET = W / "tests/test_fleetsharing_source_admission.py"
MODE = sys.argv[1]
OUT = Path(f"/tmp/source-readiness-{MODE}-instrument.json")
ORIGINAL_IDS = {
    "tests/test_fleetsharing_source_admission.py::test_original_source_reaches_real_signed_combat_put[0-0]",
    "tests/test_fleetsharing_source_admission.py::test_original_source_reaches_real_signed_combat_put[None-0]",
    "tests/test_fleetsharing_source_admission.py::test_original_source_reaches_real_signed_combat_put[7-None]",
    "tests/test_fleetsharing_source_admission.py::test_new_mailbox_does_not_replace_selected_current_ticket",
    "tests/test_fleetsharing_source_admission.py::test_cached_permission_deadline_expires_after_signing_without_utc_renewal",
    "tests/test_fleetsharing_source_admission.py::test_independent_deadlines_are_checked_after_real_leaf_wait[proof-False]",
}


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(W), *args])


original = TARGET.read_bytes()
original_hash = hashlib.sha256(original).hexdigest()
before_diff = git_bytes("diff", "--binary", "HEAD", "--", ".")
before_status = git_bytes("status", "--porcelain=v2", "--untracked-files=all", "-z")
try:
    subprocess.run(
        [sys.executable, "/tmp/source_readiness_instrument_edit.py", str(W), MODE],
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", str(TARGET)],
        cwd=W,
        check=True,
    )
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_fleetsharing_source_admission.py",
            "-q",
            "--tb=short",
        ],
        cwd=W,
        env={
            **os.environ,
            "SOURCE_READINESS_MODE": MODE,
            "SOURCE_READINESS_OUT": str(OUT),
        },
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    data = json.loads(OUT.read_text(encoding="utf-8"))
    rigs = data["rigs"]
    assert len(rigs) == 119
    assert len({row["family"] for row in rigs}) == 38
    assert Counter(row["category"] for row in rigs) == {
        "ordinary": 105,
        "ack": 4,
        "watch": 9,
        "near_expiry": 1,
    }
    expected_readiness = {
        "ordinary": (5, 7, 6),
        "ack": (6, 9, 8),
        "watch": (9, 12, 11),
        "near_expiry": (10, 12, 11),
    }
    for row in rigs:
        assert (
            row["first_ready_turn"],
            row["first_ready_real_saves"],
            row["first_ready_worker_saves"],
        ) == expected_readiness[row["category"]]
    if MODE == "baseline":
        assert sum(row["turns"] for row in rigs) == 1428
        assert sum(row["real_saves"] for row in rigs) == 1469
        assert sum(row["worker_saves"] for row in rigs) == 1350
        assert data["whole_file_real_saves"] == 1928
        assert sum(row["equality_loads"] for row in rigs) == 0
        assert not any(row["original_phase"] for row in rigs)
    elif MODE == "candidate":
        assert sum(row["turns"] for row in rigs) == 682
        assert sum(row["real_saves"] for row in rigs) == 921
        assert sum(row["worker_saves"] for row in rigs) == 802
        assert data["whole_file_real_saves"] == 1409
        assert sum(row["equality_loads"] for row in rigs) == 119
        assert {row["nodeid"] for row in rigs if row["original_phase"]} == ORIGINAL_IDS
        assert all(row["turns"] == 12 for row in rigs if row["original_phase"])
    else:
        raise AssertionError(MODE)
    report = {
        "mode": MODE,
        "target_sha256_before": original_hash,
        "rigs": len(rigs),
        "categories": dict(Counter(row["category"] for row in rigs)),
        "turns": sum(row["turns"] for row in rigs),
        "bootstrap_real_saves": sum(row["real_saves"] for row in rigs),
        "bootstrap_worker_saves": sum(row["worker_saves"] for row in rigs),
        "whole_file_real_saves": data["whole_file_real_saves"],
        "equality_loads": sum(row["equality_loads"] for row in rigs),
        "original_phase_ids": sorted(
            row["nodeid"] for row in rigs if row["original_phase"]
        ),
    }
    Path(f"/tmp/source-readiness-{MODE}-instrument-summary.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
finally:
    TARGET.write_bytes(original)
    assert TARGET.read_bytes() == original
    assert hashlib.sha256(TARGET.read_bytes()).hexdigest() == original_hash
    assert git_bytes("diff", "--binary", "HEAD", "--", ".") == before_diff
    assert (
        git_bytes("status", "--porcelain=v2", "--untracked-files=all", "-z")
        == before_status
    )
PY
python -m py_compile /tmp/source_readiness_instrument_run.py
```

Run Task 1 baseline evidence with:

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-source-admission-readiness
uv run --no-sync python /tmp/source_readiness_instrument_run.py baseline
```

Run Task 2 candidate evidence with:

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-source-admission-readiness
uv run --no-sync python /tmp/source_readiness_instrument_run.py candidate
```

Expected literal structural transition: `1428 -> 682` turns, `1469 -> 921` bootstrap real saves, `1350 -> 802` delegated saves, `1928 -> 1409` whole-file saves, and `0 -> 119` equality loads, with categories and first-ready triples unchanged and exactly six original-phase IDs at twelve turns.

## Reproducibility Block D — restoration-safe guard, fault, and production mutation matrix

This runner contains exactly 41 recipes: 18 production mutations, 5 readiness-fault probes, 4 one-turn-short bounds, and 14 equivalent valid-flow deletions. Every selected JUnit testcase is checked independently against its intended boundary; stdout is supplemental only. The exact bounded bootstrap diagnostic is accepted for readiness-fault/bound probes and rejected as masking for production mutations. Competing-expiry preconditions, barrier/thread failures, timeouts, collection/setup errors, and failures outside the exact selected IDs never qualify. Every valid-flow deletion remains explicitly equivalent/non-discriminating rather than a kill.

```bash
cat > /tmp/source_readiness_mutations.py <<'PY'
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

W = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-source-admission-readiness")
TEST = "tests/test_fleetsharing_source_admission.py"
WORKER = "wingman/fleetsharing/worker.py"
TIMING = "wingman/fleetsharing/timing.py"
BOOTSTRAP_DIAGNOSTIC = r"publication bootstrap readiness missed"
BOOTSTRAP_POSTCONDITIONS = (
    r"bootstrap state is not durable",
    r"device bootstrap is incomplete",
    r"bootstrap accepted a publication",
    r"bootstrap installed publication state",
    r"bootstrap allocated publication evidence",
    r"bootstrap allocated a publication stage floor",
)
COMPETING_EXPIRY = (
    r"MAX_SNAPSHOT_AGE_S",
    r"work\.payload\.session_deadline >",
    r"worker\._expires_at >",
    r"anchor_lifetime_ms",
    r"expires_at_mono\) >",
)
BARRIER_OR_TIMEOUT = (
    r"(?i)\b(?:timed out|not released|never reached|not reached)\b",
    r"(?im)^E\s+.*\btimeout\b",
    r"(?i)(?:AssertionError|Failed):[^\n]*\btimeout\b",
    r"assert not thread\.is_alive\(\)",
    r"assert [A-Za-z0-9_.]+\.wait\(",
)
SETUP_OR_COLLECTION = (
    r"(?i)collection error",
    r"(?i)error at setup",
    r"(?i)fixture .* failed",
)
FORBIDDEN_BY_CATEGORY = {
    "production": (
        BOOTSTRAP_DIAGNOSTIC,
        *BOOTSTRAP_POSTCONDITIONS,
        *COMPETING_EXPIRY,
        *BARRIER_OR_TIMEOUT,
        *SETUP_OR_COLLECTION,
    ),
    "readiness-fault": (
        *COMPETING_EXPIRY,
        *BARRIER_OR_TIMEOUT,
        *SETUP_OR_COLLECTION,
    ),
    "bound": (
        *COMPETING_EXPIRY,
        *BARRIER_OR_TIMEOUT,
        *SETUP_OR_COLLECTION,
    ),
    "equivalent": (),
}


@dataclass(frozen=True)
class Recipe:
    category: str
    edits: tuple[tuple[str, str, str], ...]
    nodes: tuple[str, ...]
    regex: str


RECIPES: dict[str, Recipe] = {}


def add(name, edits, nodes, regex, *, category="production"):
    assert category in FORBIDDEN_BY_CATEGORY
    assert name not in RECIPES
    RECIPES[name] = Recipe(category, tuple(edits), tuple(nodes), regex)


add(
    "final-source-admission",
    [
        (
            WORKER,
            """                    elif selected.source.admit_start(validate_publication) is not True:\n                        raise _Obsolete\n""",
            """                    elif False:\n                        raise _Obsolete\n""",
        )
    ],
    [
        TEST
        + "::test_actual_publication_barriers_fence_before_start_and_late_completion[signing-source]"
    ],
    r"assert len\(client\.puts\) ==",
)
add(
    "original-completion",
    [
        (
            WORKER,
            """        elif source.admit_start(install) is not True:\n            raise _Obsolete\n""",
            """        else:\n            install()\n""",
        )
    ],
    [
        TEST
        + "::test_original_source_guards_actual_completion_install[publication-None-True]"
    ],
    r"obsolete source acknowledged publication|isinstance\(errors\[0\], _Obsolete\)",
)
add(
    "post-save-401",
    [
        (
            WORKER,
            """            self._with_publication_source_locked(work, install)\n        for kind, event in (*notifications, (\"status\", status)):\n""",
            """            install()\n        for kind, event in (*notifications, (\"status\", status)):\n""",
        )
    ],
    [
        TEST
        + "::test_original_source_guards_post_save_401_reset[publication-reset_acquisition-True]"
    ],
    r"obsolete source reset catalogue|isinstance\(errors\[0\], _Obsolete\)",
)
rights_block = """            for rights in (\n                state.approved_capabilities,\n                state.session_approved_capabilities,\n                state.acknowledged_capabilities,\n            )\n"""
for field in (
    "approved_capabilities",
    "session_approved_capabilities",
    "acknowledged_capabilities",
):
    add(
        "held-" + field,
        [
            (
                WORKER,
                rights_block,
                rights_block.replace(f"                state.{field},\n", ""),
            )
        ],
        [
            TEST
            + f"::test_final_held_disclosure_and_applicable_withdrawal_rights[{field}-combat]"
        ],
        r"DID NOT RAISE",
    )
add(
    "proof-deadline",
    [
        (
            WORKER,
            """            or any(now >= deadline for deadline in selected.member_deadlines)\n""",
            """            or False\n""",
        )
    ],
    [
        TEST
        + "::test_cached_permission_deadline_expires_after_signing_without_utc_renewal",
        TEST
        + "::test_independent_deadlines_are_checked_after_real_leaf_wait[proof-False]",
    ],
    r"DID NOT RAISE|assert client\.puts == \[\]|isinstance\(errors\[0\], _Obsolete\)",
)
add(
    "save-before-transport",
    [
        (
            WORKER,
            """                self._persist(candidate, fence, work=work)\n                args = {\n""",
            """                if operation == "publish_snapshot":\n                    self._state = candidate\n                else:\n                    self._persist(candidate, fence, work=work)\n                args = {\n""",
        )
    ],
    [TEST + "::test_new_mailbox_does_not_replace_selected_current_ticket"],
    (
        r"assert s\.load\(self\.path\)\.last_revision == "
        r'int\(headers\["x-fleet-revision"\]\)'
    ),
)
add(
    "anchor-deadline",
    [
        (
            TIMING,
            """            now < prepared._staged_at\n            or not 0 <= 1000 * (now - m) < LIMITS[\"input_age_ms\"]\n            or anchor is None\n            or not 0\n            <= 1000 * (now - anchor.received_at)\n            <= LIMITS[\"anchor_lifetime_ms\"]\n""",
            """            now < prepared._staged_at\n            or not 0 <= 1000 * (now - m) < LIMITS[\"input_age_ms\"]\n            or anchor is None\n            or 1000 * (now - anchor.received_at) < 0\n""",
        )
    ],
    [
        TEST
        + "::test_independent_deadlines_are_checked_after_real_leaf_wait[anchor_over-False]"
    ],
    r"isinstance\(errors\[0\], _Obsolete\)|assert client\.puts == \[\]",
)
add(
    "sample-deadline",
    [
        (
            TIMING,
            """            now < prepared._staged_at\n            or not 0 <= 1000 * (now - m) < LIMITS[\"input_age_ms\"]\n            or anchor is None\n""",
            """            now < prepared._staged_at\n            or 1000 * (now - m) < 0\n            or anchor is None\n""",
        )
    ],
    [TEST + "::test_leaf_wait_crossing_original_sample_expiry_sends_nothing"],
    r"isinstance\(errors\[0\], _Obsolete\)|assert client\.puts == \[\]",
)
pin_guard = """                pin.evidence.horizon <= now\n                or self._publisher.associations.get(pin.evidence.key) is not pin\n"""
for boundary in ("row", "effect"):
    add(
        boundary + "-deadline",
        [
            (
                TIMING,
                pin_guard,
                """                False\n                or self._publisher.associations.get(pin.evidence.key) is not pin\n""",
            )
        ],
        [
            TEST
            + f"::test_independent_deadlines_are_checked_after_real_leaf_wait[{boundary}-False]"
        ],
        r"isinstance\(errors\[0\], _Obsolete\)|assert client\.puts == \[\]",
    )
add(
    "session-original-deadline",
    [
        (
            WORKER,
            "            or now >= selected.session_deadline\n",
            "            or False\n",
        ),
        (
            TEST,
            """            assert_proof_boundary_is_independent()\n            assert mono[0] <= target\n            mono[0] = target\n""",
            """            assert_proof_boundary_is_independent()\n            if boundary == \"session\":\n                worker._expires_at = Fraction(target) + 60\n            assert mono[0] <= target\n            mono[0] = target\n""",
        ),
    ],
    [
        TEST
        + "::test_independent_deadlines_are_checked_after_real_leaf_wait[session-False]"
    ],
    r"isinstance\(errors\[0\], _Obsolete\)|assert client\.puts == \[\]",
)
add(
    "uncertainty",
    [
        (
            WORKER,
            """        if len(resolved) != len(snapshot.rows) or any(\n            row.combat is None or (row.dps is None and row.incoming_dps is None)\n            for _, row in resolved\n        ):\n            return None\n""",
            """        if False:\n            return None\n""",
        )
    ],
    [
        TEST
        + "::test_any_uncertain_member_prevents_whole_inactivity_withdrawal[legacy-False-True]"
    ],
    r"destructive empty PUT|client\.puts",
)
add(
    "retry-context",
    [
        (
            WORKER,
            """                self._restart_requested = True\n            self._running = True\n""",
            """                self._restart_requested = True\n                replacement = TimingContext.__new__(TimingContext)\n                replacement.__dict__ = dict(self._timing_context.__dict__)\n                self._timing_context = replacement\n            self._running = True\n""",
        )
    ],
    [
        TEST
        + "::test_original_measurement_retry_retains_wire_origins_across_reauthentication[thread]"
    ],
    r"worker\._timing_context is context",
)
association_block = """        associations = {\n            key: pin\n            for key, pin in self._publisher.associations.items()\n            if pin.evidence.horizon > now\n        }\n"""
retry_nodes = [
    TEST
    + "::test_original_measurement_retry_retains_wire_origins_across_reauthentication[thread]",
    TEST
    + "::test_original_measurement_retry_retains_wire_origins_across_reauthentication[session]",
]
add(
    "retry-sample-pin",
    [
        (
            TIMING,
            association_block,
            association_block.replace(
                "if pin.evidence.horizon > now",
                "if pin.evidence.horizon > now and len(key) != 2",
            ),
        )
    ],
    retry_nodes,
    r"associations\[sample_key\] is original_pins\[sample_key\]",
)
add(
    "retry-row-pin",
    [
        (
            TIMING,
            association_block,
            association_block.replace(
                "if pin.evidence.horizon > now",
                'if pin.evidence.horizon > now and not (len(key) == 4 and key[2] == "row")',
            ),
        )
    ],
    retry_nodes,
    r"associations\[row_key\] is original_pins\[row_key\]",
)
add(
    "retry-effect-pin",
    [
        (
            TIMING,
            association_block,
            association_block.replace(
                "if pin.evidence.horizon > now",
                "if pin.evidence.horizon > now and not (len(key) == 4 and isinstance(key[2], tuple))",
            ),
        )
    ],
    retry_nodes,
    r"associations\[effect_key\] is original_pins\[effect_key\]",
)

semantic_observe = (
    """            observation = observe()\n            if observation[\"ready\"]:\n"""
)
object_probe = """            proof = worker._eligibility_proof\n            if proof is None:\n                observation = observe()\n            else:\n                worker._eligibility_proof = replace(\n                    proof, response=replace(worker._eligibility)\n                )\n                try:\n                    observation = observe()\n                finally:\n                    worker._eligibility_proof = proof\n            if observation[\"ready\"]:\n"""
timing_fence_probe = """            proof = worker._eligibility_proof\n            if proof is None:\n                observation = observe()\n            else:\n                current = worker._fence()\n                stale = replace(current, timing=current.timing - 1)\n                worker._eligibility_proof = replace(proof, fence=stale)\n                try:\n                    observation = observe()\n                finally:\n                    worker._eligibility_proof = proof\n            if observation[\"ready\"]:\n"""
broad_fence_probe = """            proof = worker._eligibility_proof\n            if proof is None:\n                observation = observe()\n            else:\n                current = worker._fence()\n                stale = replace(\n                    current,\n                    lifecycle=current.lifecycle - 1,\n                    identity=current.identity - 1,\n                    session=None if current.session is not None else \"stale\",\n                    participation=current.participation - 1,\n                    source=current.source + ((\"__stale__\", -1),),\n                    automatic=current.automatic - 1,\n                    timing=current.timing - 1,\n                )\n                worker._eligibility_proof = replace(proof, fence=stale)\n                try:\n                    observation = observe()\n                finally:\n                    worker._eligibility_proof = proof\n            if observation[\"ready\"]:\n"""
timing_comparison_probe = """            proof = worker._eligibility_proof\n            if proof is None:\n                observation = observe()\n            else:\n                current = worker._fence()\n                stale = replace(current, timing=current.timing - 1)\n                worker._eligibility_proof = replace(proof, fence=stale)\n                try:\n                    observation = observe()\n                finally:\n                    worker._eligibility_proof = proof\n            if observation[\"ready\"]:\n                pytest.fail(\"timing-only stale fence was accepted\")\n"""
ordinary = TEST + "::test_leaf_wait_crossing_original_sample_expiry_sends_nothing"
add(
    "readiness-exact-object",
    [(TEST, semantic_observe, object_probe)],
    [ordinary],
    r"publication bootstrap readiness missed after 12/12 turns;[\s\S]*'exact_response': False",
    category="readiness-fault",
)
add(
    "readiness-timing-fence",
    [(TEST, semantic_observe, timing_fence_probe)],
    [ordinary],
    r"fence_differences=\('timing',\)",
    category="readiness-fault",
)
add(
    "readiness-broad-fence",
    [(TEST, semantic_observe, broad_fence_probe)],
    [ordinary],
    r"fence_differences=\('lifecycle', 'identity', 'session', 'participation', 'source', 'automatic', 'timing'\)",
    category="readiness-fault",
)
add(
    "readiness-drop-timing-comparison",
    [
        (TEST, '        "timing",\n', ""),
        (TEST, semantic_observe, timing_comparison_probe),
    ],
    [ordinary],
    r"timing-only stale fence was accepted",
    category="readiness-fault",
)
add(
    "readiness-durable-mismatch",
    [
        (
            TEST,
            '    assert s.load(path) == worker._state, "bootstrap state is not durable"\n',
            """    original_bytes = path.read_bytes()\n    try:\n        s.save(path, replace(worker._state, last_revision=worker._state.last_revision + 1))\n        assert s.load(path) == worker._state, "bootstrap state is not durable"\n    finally:\n        path.write_bytes(original_bytes)\n""",
        )
    ],
    [ordinary],
    r"bootstrap state is not durable",
    category="readiness-fault",
)
for name, bound, node in (
    ("ordinary", 4, ordinary),
    (
        "ack",
        5,
        TEST
        + "::test_ack_uses_only_canonical_approved_intersection[device_caps0-session_caps0-want0]",
    ),
    (
        "watch",
        8,
        TEST
        + "::test_actual_publication_barriers_fence_before_start_and_late_completion[unwrap-source]",
    ),
    (
        "near-expiry",
        9,
        TEST
        + "::test_independent_deadlines_are_checked_after_real_leaf_wait[session-False]",
    ),
):
    add(
        "one-turn-short-" + name,
        [
            (
                TEST,
                "        for turns in range(1, 13):\n",
                f"        for turns in range(1, {bound + 1}):\n",
            )
        ],
        [node],
        rf"publication bootstrap readiness missed after {bound}/12 turns;",
        category="bound",
    )

# These valid-flow deletions are expected to pass. Record them as equivalent or
# non-discriminating review evidence; never combine them to force a kill.
for name, old, node in (
    ("guard-catalogue", '                "catalogue",\n', ordinary),
    ("guard-eligibility", '                "eligibility",\n', ordinary),
    ("guard-anchor", '                "anchor",\n', ordinary),
    ("guard-proof", '                "proof",\n', ordinary),
    ("guard-exact-response", '                "exact_response",\n', ordinary),
    ("guard-exact-fence", '                "exact_fence",\n', ordinary),
    (
        "post-durable",
        '    assert s.load(path) == worker._state, "bootstrap state is not durable"\n',
        ordinary,
    ),
    (
        "post-device",
        '    assert worker._needs_device is False, "device bootstrap is incomplete"\n',
        ordinary,
    ),
    (
        "post-puts",
        '    assert client.puts == [], "bootstrap accepted a publication"\n',
        ordinary,
    ),
    (
        "post-last-published",
        '    assert worker._last_published == (), "bootstrap installed publication state"\n',
        ordinary,
    ),
    (
        "post-associations",
        '    assert worker._timing_context._publisher.associations == {}, (\n        "bootstrap allocated publication evidence"\n    )\n',
        ordinary,
    ),
    (
        "post-next-stage",
        '    assert worker._timing_context._next_stage_at is None, (\n        "bootstrap allocated a publication stage floor"\n    )\n',
        ordinary,
    ),
):
    add(name, [(TEST, old, "")], [node], r"1 passed", category="equivalent")
watch_node = (
    TEST
    + "::test_actual_publication_barriers_fence_before_start_and_late_completion[unwrap-source]"
)
add(
    "guard-watch-source",
    [
        (
            TEST,
            '                    "source_observation",\n                    "status_source",\n                    "source_identity",\n',
            "",
        )
    ],
    [watch_node],
    r"1 passed",
    category="equivalent",
)
add(
    "guard-watch-automatic",
    [
        (
            TEST,
            '                    "automatic_observation",\n                    "status_automatic",\n                    "automatic_identity",\n',
            "",
        )
    ],
    [watch_node],
    r"1 passed",
    category="equivalent",
)

EXPECTED_RECIPE_COUNTS = {
    "production": 18,
    "readiness-fault": 5,
    "bound": 4,
    "equivalent": 14,
}
assert Counter(recipe.category for recipe in RECIPES.values()) == Counter(
    EXPECTED_RECIPE_COUNTS
)
assert len(RECIPES) == 41


class RestorationError(RuntimeError):
    pass


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(W), *args])


def junit_id(case: ET.Element) -> str:
    parts = case.get("classname", "").split(".")
    return "::".join(("/".join(parts[:2]) + ".py", *parts[2:], case.get("name", "")))


def junit_failure_text(case: ET.Element) -> str:
    failure = case.find("failure")
    assert failure is not None
    return "\n".join(
        part for part in (failure.get("message", ""), failure.text or "") if part
    )


def run_recipe(name: str) -> dict[str, object]:
    recipe = RECIPES[name]
    originals: dict[Path, bytes] = {}
    hashes: dict[str, str] = {}
    before_diff = git_bytes("diff", "--binary", "HEAD", "--", ".")
    before_status = git_bytes("status", "--porcelain=v2", "--untracked-files=all", "-z")
    output = ""
    result = "failed"
    boundary_evidence: dict[str, str] = {}
    problem = None
    restoration_problem = None
    try:
        for relative, old, new in recipe.edits:
            target = W / relative
            originals.setdefault(target, target.read_bytes())
            text = target.read_text(encoding="utf-8")
            if text.count(old) != 1:
                raise AssertionError(
                    f"{name}: {relative} exact match count {text.count(old)}"
                )
            target.write_text(text.replace(old, new), encoding="utf-8")
        junit = Path(f"/tmp/source-readiness-mutant-{name}.xml")
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *recipe.nodes,
                "-q",
                "--tb=short",
                f"--junitxml={junit}",
            ],
            cwd=W,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
        output = run.stdout + "\n" + run.stderr
        cases = list(ET.parse(junit).getroot().iter("testcase"))
        case_ids = [junit_id(case) for case in cases]
        assert case_ids == list(recipe.nodes), (name, case_ids, recipe.nodes, output)
        assert not any(case.find("error") is not None for case in cases), output
        assert not any(case.find("skipped") is not None for case in cases), output
        if recipe.category == "equivalent":
            assert run.returncode == 0, (name, run.returncode, output)
            assert not any(case.find("failure") is not None for case in cases), output
            assert re.search(recipe.regex, output), (name, recipe.regex, output)
            result = "reviewed-valid-flow-equivalent"
        else:
            assert run.returncode == 1, (name, run.returncode, output)
            for node, case in zip(recipe.nodes, cases, strict=True):
                text = junit_failure_text(case)
                assert re.search(recipe.regex, text), (
                    name,
                    node,
                    recipe.regex,
                    text,
                    output,
                )
                forbidden = tuple(
                    pattern
                    for pattern in FORBIDDEN_BY_CATEGORY[recipe.category]
                    if re.search(pattern, text)
                )
                assert not forbidden, (name, node, forbidden, text, output)
                if re.search(BOOTSTRAP_DIAGNOSTIC, text):
                    assert recipe.category in ("readiness-fault", "bound"), (
                        name,
                        node,
                        recipe.category,
                        text,
                    )
                boundary_evidence[node] = text
            # Supplemental console evidence must agree, but JUnit per-ID text is
            # the qualification authority.
            assert re.search(recipe.regex, output), (name, recipe.regex, output)
            result = "intended-red"
    except subprocess.TimeoutExpired as error:
        problem = AssertionError(f"{name}: timeout is not qualification: {error}")
        result = "invalid-timeout"
    except Exception as error:  # noqa: BLE001 — aggregate after exact restoration.
        problem = error
        result = "failed"
    finally:
        try:
            for target, original in originals.items():
                hashes[str(target.relative_to(W))] = hashlib.sha256(
                    original
                ).hexdigest()
                target.write_bytes(original)
                if target.read_bytes() != original:
                    raise RestorationError(
                        f"{name}: byte restoration failed for {target}"
                    )
                if (
                    hashlib.sha256(target.read_bytes()).hexdigest()
                    != hashes[str(target.relative_to(W))]
                ):
                    raise RestorationError(
                        f"{name}: hash restoration failed for {target}"
                    )
            if git_bytes("diff", "--binary", "HEAD", "--", ".") != before_diff:
                raise RestorationError(f"{name}: restored binary diff differs")
            if (
                git_bytes("status", "--porcelain=v2", "--untracked-files=all", "-z")
                != before_status
            ):
                raise RestorationError(f"{name}: restored status differs")
        except Exception as error:  # noqa: BLE001 — restoration failure is fatal.
            restoration_problem = error
        out = Path("/tmp/wingman-source-readiness-mutants")
        out.mkdir(exist_ok=True)
        (out / f"{name}.log").write_text(output, encoding="utf-8")
        (out / f"{name}.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "category": recipe.category,
                    "nodes": recipe.nodes,
                    "result": result,
                    "regex": recipe.regex,
                    "junit_boundaries": boundary_evidence,
                    "target_sha256": hashes,
                    "problem": None if problem is None else repr(problem),
                    "restoration_problem": None
                    if restoration_problem is None
                    else repr(restoration_problem),
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if restoration_problem is not None:
        raise RestorationError(str(restoration_problem))
    if problem is not None:
        raise problem
    return {
        "name": name,
        "category": recipe.category,
        "result": result,
        "nodes": recipe.nodes,
    }


def main(argv: list[str]) -> int:
    names = tuple(RECIPES) if argv == ["--all"] else tuple(argv)
    assert names and not (set(names) - set(RECIPES)), names
    failures = []
    for name in names:
        try:
            report = run_recipe(name)
        except RestorationError:
            raise
        except Exception as error:  # noqa: BLE001 — continue ordinary recipe failures.
            failures.append((name, repr(error)))
            report = {"name": name, "result": "failed", "error": repr(error)}
        print(json.dumps(report, sort_keys=True))
    if failures:
        print(json.dumps({"failures": failures}, sort_keys=True), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "recipes": len(names),
                "categories": dict(Counter(RECIPES[name].category for name in names)),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
PY
python -m py_compile /tmp/source_readiness_mutations.py
uv run --extra dev ruff check /tmp/source_readiness_mutations.py
uv run --extra dev ruff format --check /tmp/source_readiness_mutations.py
```

Run all 41 recipes in insertion order in one aggregate invocation:

```bash
uv run --no-sync python /tmp/source_readiness_mutations.py --all
```

Expected:

- the summary is exactly `41` recipes classified as production `18`, readiness-fault `5`, bound `4`, and equivalent `14`;
- every production/readiness-fault/bound recipe reports `intended-red`, and every selected JUnit testcase independently matches the recipe's intended boundary regex;
- only readiness-fault/bound recipes may contain the exact bounded bootstrap diagnostic; any production bootstrap readiness diagnostic or common postcondition failure is rejected as masking;
- `save-before-transport` changes only the `publish_snapshot` reservation, retains `_persist` for every other signed operation, and fails at `PublicationClient.transport`'s fresh-disk `last_revision` versus `x-fleet-revision` assertion;
- every selected failure lacks its category's competing-expiry, barrier/thread, timeout, setup, and collection signatures;
- the timing-only fence fault names exactly `fence_differences=('timing',)`, the broad fence fault names all seven fields in order, and deleting the timing comparison is killed by `timing-only stale fence was accepted`;
- both retry rows fail for sample, row, and isolated effect-pin drops at their exact identity assertion;
- the session recipe removes only the selected-original session guard and makes the competing current cache later, so the held session identity fails at the session refusal rather than another deadline;
- all 14 guard/postcondition deletions report `reviewed-valid-flow-equivalent`; do not call them kills;
- every recipe restores bytes, hashes, full binary diff, and NUL status exactly.

---

## Reproducibility Block E — exact endpoint identity and four order runs

```bash
cat > /tmp/source_readiness_endpoint.py <<'PY'
from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import random
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

W = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-source-admission-readiness")
B = Path("/tmp/wingman-source-readiness-baseline")
BASE = "f6e8ecd5b09889e79aa169ce103b2eb9681cec9f"
FILES = [
    "tests/test_fleetsharing_source_admission.py",
    "tests/test_fleetsharing_remote_worker.py",
    "tests/test_fleetsharing_worker_fix1.py",
]
EXPECTED_HASHES = {
    "normal": "7b9e3644793a89952f132df22b1131c699530c41357b0f92fe4f80873faae89d",
    "reverse-file": "8890f6fe56c31201dfddc19054f51de8e8beb6be06ae94d63d98945e148c3a9b",
    "reverse-node": "8acc488cd820e8f289dfaf003c2900fa5f4b63f0d52eb9653af8067d4978c809",
    "shuffle": "2c8be0cd05e8cfb3e1ce5fa4f650cc7049dabf1069d2a95af861317911fd0a0a",
}


def digest(nodes):
    return hashlib.sha256(("\n".join(nodes) + "\n").encode()).hexdigest()


def extract(root):
    raw = subprocess.check_output(["git", "-C", str(W), "archive", BASE])
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        archive.extractall(root, filter="data")


def collect(root, args, output):
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *args,
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "source_readiness_collection_plugin",
        ],
        cwd=root,
        env={
            **os.environ,
            "PYTHONPATH": f"{root}:/tmp",
            "SOURCE_READINESS_COLLECTION_OUT": str(output),
        },
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return [row["nodeid"] for row in json.loads(output.read_text(encoding="utf-8"))]


def shape(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        {
            "name": node.name,
            "args": [argument.arg for argument in node.args.args],
            "posonlyargs": [argument.arg for argument in node.args.posonlyargs],
            "kwonlyargs": [argument.arg for argument in node.args.kwonlyargs],
            "vararg": node.args.vararg.arg if node.args.vararg else None,
            "kwarg": node.args.kwarg.arg if node.args.kwarg else None,
            "decorators": [
                ast.dump(value, include_attributes=False)
                for value in node.decorator_list
            ],
        }
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


def junit_id(case):
    parts = case.get("classname", "").split(".")
    return "::".join(("/".join(parts[:2]) + ".py", *parts[2:], case.get("name", "")))


def run_order(name, nodes):
    junit = Path(f"/tmp/source-readiness-order-{name}.xml")
    run = subprocess.run(
        [sys.executable, "-m", "pytest", *nodes, "-q", "-rs", f"--junitxml={junit}"],
        cwd=W,
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    cases = list(ET.parse(junit).getroot().iter("testcase"))
    observed = [junit_id(case) for case in cases]
    assert observed == nodes
    assert len(observed) == len(set(observed)) == 167
    assert not any(case.find("skipped") is not None for case in cases)
    return {"name": name, "count": len(observed), "sha256": digest(observed)}


baseline_target = (B / "source-120.txt").read_text(encoding="utf-8").splitlines()
baseline_complete = (B / "complete-16609.txt").read_text(encoding="utf-8").splitlines()
baseline_shape = json.loads((B / "source-shape.json").read_text(encoding="utf-8"))
current_target = collect(
    W, [FILES[0]], Path("/tmp/source-readiness-current-target.json")
)
current_complete = collect(
    W, ["tests"], Path("/tmp/source-readiness-current-complete.json")
)
assert current_target == baseline_target
assert current_complete == baseline_complete
assert shape(W / FILES[0]) == baseline_shape
assert (
    hashlib.sha256((W / FILES[1]).read_bytes()).hexdigest()
    == "d77a1fa8c0919de4cca443f5f823407ce46461fb5104352853a90df9a25205b7"
)
assert (
    hashlib.sha256((W / FILES[2]).read_bytes()).hexdigest()
    == "cc3dfe364f8754ebb34d7bedfc16a0eee64349391406161e680f08a7be444b25"
)

with tempfile.TemporaryDirectory(
    prefix="source-readiness-order-baseline-"
) as directory:
    baseline_root = Path(directory)
    extract(baseline_root)
    normal = collect(
        baseline_root, FILES, Path("/tmp/source-readiness-baseline-167.json")
    )
current_normal = collect(W, FILES, Path("/tmp/source-readiness-current-167.json"))
assert current_normal == normal
assert len(normal) == len(set(normal)) == 167

groups = [
    [node for node in normal if node.startswith(file_name + "::")]
    for file_name in FILES
]
orders = {
    "normal": normal,
    "reverse-file": [node for group in reversed(groups) for node in group],
    "reverse-node": list(reversed(normal)),
}
orders["shuffle"] = list(normal)
random.Random(20260925).shuffle(orders["shuffle"])
assert {name: digest(nodes) for name, nodes in orders.items()} == EXPECTED_HASHES
reports = [run_order(name, nodes) for name, nodes in orders.items()]
assert {row["name"]: row["sha256"] for row in reports} == EXPECTED_HASHES
print(
    json.dumps(
        {
            "source": len(current_target),
            "complete": len(current_complete),
            "orders": reports,
        },
        sort_keys=True,
    )
)
PY
python -m py_compile /tmp/source_readiness_endpoint.py
uv run --extra dev ruff check /tmp/source_readiness_endpoint.py
uv run --extra dev ruff format --check /tmp/source_readiness_endpoint.py
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-source-admission-readiness
uv run --no-sync python /tmp/source_readiness_endpoint.py
```

Expected: exact source `120`, complete `16609`, unchanged AST decorators/signatures, unchanged caller bytes, exact 167 identities, and four green one-shot order runs with the four frozen hashes. Do not retry an order to green.

## Reproducibility Block F — explicit, rerun-aware hosted collector and audit

Run this block only after the Task 5 authorization stop is explicitly lifted. `REVIEWED_HEAD`, `NEW_RUN`, and `PR_NUMBER` are mandatory literal inputs; the script never infers “latest” or silently substitutes the current remote head. It requires a clean local worktree at the frozen reviewed commit, binds the PR head, run head, job heads, checkout-log executable head, and artifact heads to that exact SHA, records every attempt, treats checkout logs as primary synthetic/head/base evidence, permits an empty run `pull_requests` array only with explicit current PR corroboration, selects artifacts by exact name/head/time window, and compares exact identities/skips with Task 1.

```bash
cat > /tmp/source_readiness_hosted.py <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

R = "elboaf/FlyGD-Wingman"
W = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-source-admission-readiness")
B = Path("/tmp/wingman-source-readiness-baseline")
REVIEWED_HEAD = os.environ["REVIEWED_HEAD"]
RUN_ID = int(os.environ["NEW_RUN"])
PR_NUMBER = int(os.environ["PR_NUMBER"])
OUT = Path(f"/tmp/wingman-source-readiness-hosted-{RUN_ID}")
TARGET = "tests/test_fleetsharing_source_admission.py"
THREE = {
    TARGET,
    "tests/test_fleetsharing_remote_worker.py",
    "tests/test_fleetsharing_worker_fix1.py",
}
EXPECTED_PATHS = {
    "docs/superpowers/specs/2026-09-25-source-admission-readiness-bootstrap-design.md",
    "docs/superpowers/plans/2026-09-25-source-admission-readiness-bootstrap.md",
    "docs/ci-source-admission-readiness-bootstrap-results.md",
    TARGET,
}


def command(*args: str, text=True) -> str | bytes:
    return subprocess.check_output(args, text=text)


assert re.fullmatch(r"[0-9a-f]{40}", REVIEWED_HEAD)
assert (
    command("git", "-C", str(W), "rev-parse", "HEAD", text=True).strip()
    == REVIEWED_HEAD
)
assert (
    command(
        "git",
        "-C",
        str(W),
        "status",
        "--porcelain=v2",
        "--untracked-files=all",
        text=True,
    )
    == ""
)


def gh_json(*args: str):
    return json.loads(command("gh", *args, text=True))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def nodes_digest(nodes: list[str]) -> str:
    return digest(("\n".join(nodes) + "\n").encode())


def identity(case: ET.Element) -> str:
    parts = case.get("classname", "").split(".")
    assert len(parts) >= 2 and parts[0] == "tests", parts
    return "::".join(("/".join(parts[:2]) + ".py", *parts[2:], case.get("name", "")))


def normalized_skip(text: str) -> str:
    return re.sub(
        r"pytest-of-[^/\s]+/pytest-\d+/[^\s:\"']+",
        "pytest-of-USER/pytest-N/PYTEST_TMP",
        text.replace("\\", "/"),
    )


def dt(text: str) -> datetime:
    return datetime.fromisoformat(text)


def seconds(start: str, end: str) -> float:
    return (dt(end) - dt(start)).total_seconds()


def checkout_evidence(text: str) -> tuple[str, str, str]:
    lines = text.splitlines()
    merge_pattern = re.compile(
        r"HEAD is now at (?P<short>[0-9a-f]{7,40}) Merge "
        r"(?P<head>[0-9a-f]{40}) into (?P<base>[0-9a-f]{40})"
    )
    full_pattern = re.compile(r"(?P<sha>[0-9a-f]{40})\s*$")
    merges = [match for line in lines if (match := merge_pattern.search(line))]
    commands = [
        index
        for index, line in enumerate(lines)
        if "[command]" in line and "log -1 --format=%H" in line
    ]
    assert len(merges) == len(commands) == 1, (merges, commands)
    full = full_pattern.search(lines[commands[0] + 1])
    assert full
    synthetic = full.group("sha")
    assert synthetic.startswith(merges[0].group("short"))
    return synthetic, merges[0].group("head"), merges[0].group("base")


def parse_platform(
    platform: str, root: Path, baseline_ids, baseline_target, baseline_skips
):
    xml_path = root / "pytest-result.xml"
    timing_path = root / "pytest-timing.json"
    cases = list(ET.parse(xml_path).getroot().iter("testcase"))
    ids = [identity(case) for case in cases]
    assert ids == baseline_ids
    assert len(ids) == len(set(ids)) == 16609
    failures = {identity(case) for case in cases if case.find("failure") is not None}
    errors = {identity(case) for case in cases if case.find("error") is not None}
    skips = [
        (
            identity(case),
            normalized_skip(
                case.find("skipped").get("message") or case.find("skipped").text or ""
            ),
        )
        for case in cases
        if case.find("skipped") is not None
    ]
    assert not failures and not errors
    assert skips == baseline_skips
    target_rows = [
        (identity(case), float(case.get("time", "0") or 0))
        for case in cases
        if identity(case).startswith(TARGET + "::")
    ]
    assert [node for node, _ in target_rows] == baseline_target
    assert len(target_rows) == 120
    three_rows = [
        (identity(case), float(case.get("time", "0") or 0))
        for case in cases
        if identity(case).split("::", 1)[0] in THREE
    ]
    baseline_three = [node for node in baseline_ids if node.split("::", 1)[0] in THREE]
    assert [node for node, _ in three_rows] == baseline_three
    assert len(three_rows) == 167
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    assert timing["case_count"] == 16609
    source_timing = timing["files"][TARGET]
    assert source_timing["cases"] == 120
    assert abs(source_timing["seconds"] - sum(value for _, value in target_rows)) < 1e-9
    three_seconds = sum(timing["files"][file_name]["seconds"] for file_name in THREE)
    return {
        "platform": platform,
        "case_count": len(ids),
        "complete_sha256": nodes_digest(ids),
        "source_count": len(target_rows),
        "source_sha256": nodes_digest([node for node, _ in target_rows]),
        "source_seconds": sum(value for _, value in target_rows),
        "source_slowest": sorted(target_rows, key=lambda row: row[1], reverse=True)[
            :20
        ],
        "three_file_count": len(three_rows),
        "three_file_sha256": nodes_digest([node for node, _ in three_rows]),
        "three_file_seconds": three_seconds,
        "passed": len(ids) - len(skips),
        "skipped": len(skips),
        "xml_sha256": digest(xml_path.read_bytes()),
        "timing_sha256": digest(timing_path.read_bytes()),
    }


OUT.mkdir(exist_ok=False)
(OUT / "logs").mkdir()
(OUT / "artifacts").mkdir()
run = gh_json("api", f"repos/{R}/actions/runs/{RUN_ID}")
attempt = int(run["run_attempt"])
assert run["event"] == "pull_request"
assert run["status"] == "completed" and run["conclusion"] == "success"
assert run["id"] == RUN_ID
(OUT / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
attempts = {}
for number in range(1, attempt + 1):
    attempts[number] = gh_json(
        "api", f"repos/{R}/actions/runs/{RUN_ID}/attempts/{number}"
    )
    (OUT / f"run-attempt-{number}.json").write_text(
        json.dumps(attempts[number], indent=2) + "\n", encoding="utf-8"
    )
current_jobs = gh_json(
    "api", f"repos/{R}/actions/runs/{RUN_ID}/attempts/{attempt}/jobs?per_page=100"
)["jobs"]
(OUT / "jobs.json").write_text(
    json.dumps(current_jobs, indent=2) + "\n", encoding="utf-8"
)
pr = gh_json(
    "pr",
    "view",
    str(PR_NUMBER),
    "-R",
    R,
    "--json",
    "number,url,headRefName,headRefOid,baseRefName,baseRefOid,state,mergedAt",
)
assert pr["number"] == PR_NUMBER and pr["baseRefName"] == "main"
assert pr["state"] == "OPEN" and pr["mergedAt"] is None
assert pr["headRefOid"] == run["head_sha"] == REVIEWED_HEAD
(OUT / "pr.json").write_text(json.dumps(pr, indent=2) + "\n", encoding="utf-8")
roles = {
    "checks": "checks",
    "ubuntu": "test (ubuntu-latest)",
    "windows": "test (windows-latest)",
}
jobs = {}
checkout = set()
for role, name in roles.items():
    rows = [job for job in current_jobs if job["name"] == name]
    assert len(rows) == 1, (role, rows)
    job = rows[0]
    assert job["run_attempt"] == attempt
    assert job["status"] == "completed" and job["conclusion"] == "success"
    assert job["head_sha"] == run["head_sha"] == pr["headRefOid"] == REVIEWED_HEAD
    log = command(
        "gh",
        "run",
        "view",
        str(RUN_ID),
        "-R",
        R,
        "--job",
        str(job["id"]),
        "--log",
        text=True,
    )
    (OUT / "logs" / f"{role}.log").write_text(log, encoding="utf-8")
    checkout.add(checkout_evidence(log))
    jobs[role] = job
assert len(checkout) == 1
synthetic, head, base = checkout.pop()
assert head == run["head_sha"] == pr["headRefOid"] == REVIEWED_HEAD
assert base == pr["baseRefOid"]
run_prs = run.get("pull_requests") or []
if run_prs:
    assert len(run_prs) == 1 and run_prs[0]["number"] == PR_NUMBER
    run_pr_metadata = "present"
else:
    run_pr_metadata = "absent"

subprocess.run(
    [
        "git",
        "-C",
        str(W),
        "fetch",
        "--quiet",
        "--no-tags",
        "origin",
        synthetic,
        head,
        base,
    ],
    check=True,
)
parents = command(
    "git", "-C", str(W), "rev-list", "--parents", "-n", "1", synthetic, text=True
).split()
assert parents == [synthetic, base, head]
paths = set(
    command(
        "git",
        "-C",
        str(W),
        "diff",
        "--name-only",
        base,
        synthetic,
        "--",
        ".",
        text=True,
    ).splitlines()
)
assert paths == EXPECTED_PATHS, sorted(paths ^ EXPECTED_PATHS)

pages = gh_json(
    "api",
    "--paginate",
    f"repos/{R}/actions/runs/{RUN_ID}/artifacts?per_page=100",
    "--slurp",
)
artifacts = [artifact for page in pages for artifact in page["artifacts"]]
selected_artifacts = {}
for role, name in (
    ("ubuntu", "pytest-evidence-ubuntu-latest"),
    ("windows", "pytest-evidence-windows-latest"),
):
    job = jobs[role]
    rows = [
        artifact
        for artifact in artifacts
        if artifact["name"] == name
        and not artifact["expired"]
        and artifact["workflow_run"]["id"] == RUN_ID
        and artifact["workflow_run"]["head_sha"] == head
        and dt(job["started_at"])
        <= dt(artifact["created_at"])
        <= dt(job["completed_at"])
    ]
    assert len(rows) == 1, (role, rows)
    artifact = rows[0]
    archive = command("gh", "api", artifact["archive_download_url"], text=False)
    assert "sha256:" + digest(archive) == artifact["digest"]
    zip_path = OUT / "artifacts" / f"{role}.zip"
    zip_path.write_bytes(archive)
    target = OUT / "artifacts" / role
    target.mkdir()
    with zipfile.ZipFile(zip_path) as package:
        assert set(package.namelist()) == {"pytest-result.xml", "pytest-timing.json"}
        package.extractall(target)
    selected_artifacts[role] = artifact

baseline_ids = (B / "complete-16609.txt").read_text(encoding="utf-8").splitlines()
baseline_target = (B / "source-120.txt").read_text(encoding="utf-8").splitlines()
platforms = {}
for role in ("ubuntu", "windows"):
    baseline_skips = [
        tuple(row)
        for row in json.loads((B / f"{role}-skips.json").read_text(encoding="utf-8"))
    ]
    platforms[role] = parse_platform(
        role, OUT / "artifacts" / role, baseline_ids, baseline_target, baseline_skips
    )
assert (
    platforms["ubuntu"]["complete_sha256"]
    == platforms["windows"]["complete_sha256"]
    == "f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100"
)
assert (
    platforms["ubuntu"]["source_sha256"]
    == platforms["windows"]["source_sha256"]
    == "b79e5648f77c4e9af985085209b66a3b306c2ec56635a4b2a7586de21713a488"
)
assert (platforms["ubuntu"]["passed"], platforms["ubuntu"]["skipped"]) == (16595, 14)
assert (platforms["windows"]["passed"], platforms["windows"]["skipped"]) == (16542, 67)

job_report = {}
for role, job in jobs.items():
    test_steps = [step for step in job["steps"] if step["name"] == "Test"]
    job_report[role] = {
        "job_id": job["id"],
        "job_seconds": seconds(job["started_at"], job["completed_at"]),
        "test_step_seconds": seconds(
            test_steps[0]["started_at"], test_steps[0]["completed_at"]
        )
        if test_steps
        else None,
    }
report = {
    "run": RUN_ID,
    "attempt": attempt,
    "attempt_conclusions": {
        str(number): value["conclusion"] for number, value in attempts.items()
    },
    "pr": PR_NUMBER,
    "reviewed_head": REVIEWED_HEAD,
    "synthetic": synthetic,
    "head": head,
    "base": base,
    "run_pull_request_metadata": run_pr_metadata,
    "paths": sorted(paths),
    "jobs": job_report,
    "artifacts": {
        role: {
            "id": artifact["id"],
            "digest": artifact["digest"],
            "created_at": artifact["created_at"],
        }
        for role, artifact in selected_artifacts.items()
    },
    "platforms": platforms,
    "identity_change": {
        "source_added": 0,
        "source_removed": 0,
        "complete_added": 0,
        "complete_removed": 0,
    },
    "structural_claim": {
        "turns": "1428 -> 682",
        "bootstrap_real_saves": "1469 -> 921",
        "bootstrap_worker_saves": "1350 -> 802",
        "whole_file_real_saves": "1928 -> 1409",
        "equality_loads": "0 -> 119",
    },
    "claim": "identity-preserving structural work reduction; timings are observations only and no speedup is claimed",
}
(OUT / "hosted-audit.json").write_text(
    json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(report, sort_keys=True))
PY
python -m py_compile /tmp/source_readiness_hosted.py
uv run --extra dev ruff check /tmp/source_readiness_hosted.py
uv run --extra dev ruff format --check /tmp/source_readiness_hosted.py
```

After explicit authorization supplies the literal frozen SHA printed by Task 5 plus the literal run and PR numbers:

```bash
read -r REVIEWED_HEAD NEW_RUN PR_NUMBER
export REVIEWED_HEAD NEW_RUN PR_NUMBER
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-source-admission-readiness
uv run --no-sync python /tmp/source_readiness_hosted.py
```

Expected hosted acceptance:

- the local worktree is clean at the exact 40-character `REVIEWED_HEAD` frozen after the final local commit;
- PR, run, all three required jobs, checkout-log executable head, and artifact heads bind to that exact reviewed SHA; every prior attempt conclusion remains recorded;
- checkout logs agree on synthetic/head/base; synthetic parents are exact base/head;
- empty run PR metadata is recorded as `absent` rather than guessed, while explicit current PR metadata is authoritative;
- synthetic diff is exactly the four committed paths;
- Ubuntu and Windows each retain exact ordered source `120` and complete `16609` identities with additions/removals `+0/0`;
- complete normalized skips equal Task 1 exactly: Ubuntu `16595 + 14`, Windows `16542 + 67`;
- the full-suite three-file subset is exactly 167 identities on each platform;
- source, three-file, job, and Test-step durations are observations only;
- structural turns/saves/loads come from the real local instrumentation and are not inferred from hosted timing.

---

### Task 1: Freeze the `f6e8ecd5` / PR #289 Baseline

**Files:**
- Create: `docs/ci-source-admission-readiness-bootstrap-results.md`
- Read: `docs/ci-test-budget-redesign.md`
- Read: `docs/ci-test-budget-fleet-tranche-results.md`
- Read: `docs/history/2026-09-21-ci-test-budget-fleet-tranche.md`
- Read: `tests/test_fleetsharing_source_admission.py`
- Read: `tests/test_fleetsharing_remote_worker.py`
- Read: `tests/test_fleetsharing_worker_fix1.py`
- Read: `/tmp/wingman-windows-memory-hosted-36147950569/{selected.json,hosted-audit.json,logs/*,artifacts/{windows,ubuntu}/*}`

**Interfaces:**
- Consumes: merged baseline `f6e8ecd5`, PR #289 run `36147950569` attempt 2, exact artifact roots, current worker/state/timing helpers.
- Produces: immutable baseline ledgers under `/tmp/wingman-source-readiness-baseline` and the committed results document with exact IDs, families, instrumentation, provenance, skips, and timing observations.

- [ ] **Step 1: Verify branch/base and clean protected scope**

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-source-admission-readiness
git status --short --branch
git log -5 --oneline --decorate
git merge-base origin/main HEAD
git diff --check
```

Expected: branch `ci-source-admission-readiness`, base ancestry includes `f6e8ecd5`, only the approved spec/plan history is present, and no test/production mutation exists.

- [ ] **Step 2: Materialize and run Reproducibility Block A**

Run the exact Block A commands. Expected literal endpoint is target `120`, complete `16609`, 39 families, source hash `b79e5648f77c4e9af985085209b66a3b306c2ec56635a4b2a7586de21713a488`, complete hash `f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100`, Windows `14.150s`, Ubuntu `2.835s`, exact PR #289 provenance, and exact normalized skips.

- [ ] **Step 3: Materialize Block C and run real baseline instrumentation**

```bash
uv run --no-sync python /tmp/source_readiness_instrument_run.py baseline
```

Expected: 119 rigs, 38 rig-owning families plus the known no-rig family, categories `105/4/9/1`, readiness triples `5/7/6`, `6/9/8`, `9/12/11`, `10/12/11`, and baseline totals `1428/1469/1350/1928/0`. The source bytes/diff/status restore exactly.

- [ ] **Step 4: Create the results ledger from exact outputs**

Create `docs/ci-source-admission-readiness-bootstrap-results.md` with these sections in this order:

1. `Authority and source identities`
2. `PR #289 provenance and artifacts`
3. `Exact platform outcomes and skips`
4. `Family and construction inventory`
5. `Baseline structural instrumentation`
6. `Implementation and TDD evidence`
7. `Guard deletions, fault probes, and production mutations`
8. `Identity and order verification`
9. `Complete local verification`
10. `Hosted comparison`
11. `Scope, restoration, reviews, and concerns`
12. the exact `identity-appendices.md` content from Block A.

Record the exact baseline values from Global Constraints and Block A/C; do not enter estimates. State that all timing values are observations and no speedup is claimed.

- [ ] **Step 5: Review baseline evidence against source and artifacts**

Use the `requesting-code-review` skill for one independent read-only review of the results ledger, Block A output, both JUnit/timing files, `selected.json`, all three current logs, the failed attempt-1 record, and Block C output. The review must explicitly check rerun provenance, empty PR metadata handling, ID order/hashes, 39 families, 119 rigs, category arithmetic, skip normalization, artifact digest/ZIP equality, and claim discipline. Resolve every valid finding.

- [ ] **Step 6: Verify documentation-only Task 1 scope and commit**

```bash
git diff --check
git status --short
git diff --name-only HEAD -- .
git add docs/ci-source-admission-readiness-bootstrap-results.md
git diff --cached --name-only
git commit -m "docs: freeze source admission readiness baseline"
```

Expected staged path: only `docs/ci-source-admission-readiness-bootstrap-results.md`.

---

### Task 2: TDD the Readiness Bootstrap and Permission Preconditions

**Files:**
- Modify: `tests/test_fleetsharing_source_admission.py`
- Modify: `docs/ci-source-admission-readiness-bootstrap-results.md`
- Verify unchanged: `tests/test_fleetsharing_remote_worker.py`
- Verify unchanged: `tests/test_fleetsharing_worker_fix1.py`

**Interfaces:**
- Consumes: Task 1 exact IDs/shapes/counts and Block B permanent interface.
- Produces: bounded readiness helper, keyword-only `original_phase=False`, exactly six phase-preserving identities, common postconditions, independent proof preconditions, exact candidate structural counts, and green 120/167 order evidence.

- [ ] **Step 1: Validate the complete candidate in a disposable archived assembly**

Extract `f6e8ecd5` under the fresh disposable directory `/tmp/source-readiness-candidate-assembly`, assert that path does not already exist, apply every Block B snippet there, run Ruff formatting, then run:

```bash
python -m py_compile tests/test_fleetsharing_source_admission.py
ruff check tests/test_fleetsharing_source_admission.py
ruff format --check tests/test_fleetsharing_source_admission.py
python -m pytest tests/test_fleetsharing_source_admission.py -q --tb=short
```

Expected: script and module compile, Ruff passes, and all 120 identities pass in the disposable tree. Do not copy generated caches or evidence into the worktree.

- [ ] **Step 2: Establish RED through the existing identities**

Edit only the fixture signature/delegation and the four explicit original-phase source expressions first, but do not define `_drive_publication_bootstrap` yet. Run one representative from each class:

```bash
uv run --no-sync python -m pytest \
  'tests/test_fleetsharing_source_admission.py::test_leaf_wait_crossing_original_sample_expiry_sends_nothing' \
  'tests/test_fleetsharing_source_admission.py::test_ack_uses_only_canonical_approved_intersection[device_caps0-session_caps0-want0]' \
  'tests/test_fleetsharing_source_admission.py::test_actual_publication_barriers_fence_before_start_and_late_completion[unwrap-source]' \
  'tests/test_fleetsharing_source_admission.py::test_independent_deadlines_are_checked_after_real_leaf_wait[session-False]' \
  'tests/test_fleetsharing_source_admission.py::test_original_source_reaches_real_signed_combat_put[0-0]' \
  -q --tb=short
```

Expected: all five fail with `NameError: _drive_publication_bootstrap is not defined`; collection IDs and signatures remain unchanged.

- [ ] **Step 3: Implement the minimal helper and common postconditions**

Add the exact Block B imports/helper/fixture. Run the same five identities. Expected: all pass, ordinary/ACK/watch/near-expiry stop at semantic readiness, and the original-phase row retains its exact timestamp/body.

- [ ] **Step 4: Add the exact six original-phase choices and proof preconditions**

Apply the remaining Block B call expressions and both competing-deadline precondition blocks. Run:

```bash
uv run --no-sync python -m pytest \
  'tests/test_fleetsharing_source_admission.py::test_original_source_reaches_real_signed_combat_put' \
  'tests/test_fleetsharing_source_admission.py::test_new_mailbox_does_not_replace_selected_current_ticket' \
  'tests/test_fleetsharing_source_admission.py::test_cached_permission_deadline_expires_after_signing_without_utc_renewal' \
  'tests/test_fleetsharing_source_admission.py::test_independent_deadlines_are_checked_after_real_leaf_wait[proof-False]' \
  -q --tb=short
```

Expected: exactly six cases pass; the first four retain `sampled_at_ms == 1788782405800`, and both permission refusals still produce `_Obsolete` with every competing deadline admissible.

- [ ] **Step 5: Run readiness fault probes and one-turn-short bounds**

Materialize Block D and run only:

```bash
uv run --no-sync python /tmp/source_readiness_mutations.py \
  readiness-exact-object readiness-timing-fence readiness-broad-fence \
  readiness-drop-timing-comparison readiness-durable-mismatch \
  one-turn-short-ordinary one-turn-short-ack one-turn-short-watch \
  one-turn-short-near-expiry
```

Expected: exact-object diagnostic names `exact_response=False`; the timing-only fault names exactly `fence_differences=('timing',)`; the separate broad fault names all seven fence fields; deleting only the timing comparison fails at `timing-only stale fence was accepted`; durable mismatch fails the fresh equality assertion after exact file-byte restoration; bounds `4/5/8/9` fail representatives whose true first-ready turns are `5/6/9/10`. Every selected JUnit testcase independently matches that intended boundary and contains no category-forbidden competing expiry, barrier/thread, timeout, setup, or collection signature.

- [ ] **Step 6: Run valid-flow guard deletion review**

```bash
uv run --no-sync python /tmp/source_readiness_mutations.py \
  guard-catalogue guard-eligibility guard-anchor guard-proof \
  guard-exact-response guard-exact-fence guard-watch-source \
  guard-watch-automatic post-durable post-device post-puts \
  post-last-published post-associations post-next-stage
```

Expected: every row reports `reviewed-valid-flow-equivalent`. Record that result without calling it a kill; retain the named checks for diagnostics/postconditions and rely on exact faults for response/fence/durability.

- [ ] **Step 7: Run all 120 cases and exact candidate instrumentation**

```bash
uv run --no-sync python -m pytest tests/test_fleetsharing_source_admission.py \
  -q -rs --durations=30 --junitxml=/tmp/source-readiness-task2.xml
uv run --no-sync python /tmp/source_readiness_instrument_run.py candidate
```

Expected: `120 passed`; candidate totals `682/921/802/1409/119`; exact six original-phase IDs at 12 turns; categories and first-ready triples unchanged.

- [ ] **Step 8: Run exact endpoint collection and four order runs**

Materialize Block E and run it. Expected: source 120/full 16609 collection unchanged, callers byte-identical, three-file 167 unchanged, and all four order hashes green without retries.

- [ ] **Step 9: Record Task 2 evidence and review**

Append the RED/GREEN commands, exact helper interface, diagnostics, six IDs, proof preconditions, fault results, guard-deletion classification, structural transition, 120 run, and four order reports to the results ledger. Use `requesting-code-review` for an independent review focused on full fence fields, watch authority, common postconditions, original-phase count, exact timestamps, no `_work()`/`_publication()`, and unchanged callers. Resolve findings and rerun affected checks.

- [ ] **Step 10: Verify and commit Task 2**

```bash
uv run --extra dev ruff check tests/test_fleetsharing_source_admission.py
uv run --extra dev ruff format --check tests/test_fleetsharing_source_admission.py
git diff --check
git diff --exit-code -- tests/test_fleetsharing_remote_worker.py tests/test_fleetsharing_worker_fix1.py
git add tests/test_fleetsharing_source_admission.py docs/ci-source-admission-readiness-bootstrap-results.md
git diff --cached --name-only
git commit -m "test: add source admission readiness bootstrap"
```

Expected staged paths: only the source-admission test and results ledger.

---

### Task 3: Strengthen Retry Identities and Run the Full Mutation Matrix

**Files:**
- Modify: `tests/test_fleetsharing_source_admission.py`
- Modify: `docs/ci-source-admission-readiness-bootstrap-results.md`
- Temporarily mutate and restore: `wingman/fleetsharing/worker.py`
- Temporarily mutate and restore: `wingman/fleetsharing/timing.py`

**Interfaces:**
- Consumes: Task 2 helper/preconditions and Block D restoration runner.
- Produces: exact three-key/pin retry assertions and complete assertion-level qualification of retained publication authority.

- [ ] **Step 1: Establish RED for the named effect and exact keys**

Apply the complete retry replacement from Block B, but for the RED run change only the effect name component by defining this concrete accepted-effect-derived tuple and using it in `expected_keys`:

```python
wrong_effect_key = (
    character_id,
    accepted_effect.observation_id[0],
    (accepted_effect.kind, None),
    accepted_effect.observation_id,
)
expected_keys = frozenset((sample_key, row_key, wrong_effect_key))
```

Do not use free `lifetime`, `kind`, or `observation_id` identifiers. Run both retry rows:

```bash
uv run --no-sync python -m pytest \
  'tests/test_fleetsharing_source_admission.py::test_original_measurement_retry_retains_wire_origins_across_reauthentication' \
  -q --tb=short
```

Expected: both fail at `frozenset(associations) == expected_keys`, proving the assertion reads the accepted named-effect key. Restore `expected_keys = frozenset((sample_key, row_key, effect_key))` immediately; no other tuple component changes.

- [ ] **Step 2: Add exact retained pin identity and run GREEN**

Apply all retry snippets from Block B and run both rows again. Expected: `2 passed`; key set is exactly sample/row/effect, cardinality exactly 3, all three post-retry pins are identical objects, repeated wire body/context/floor/latest-source assertions remain, and the session row still changes durable session ID.

- [ ] **Step 3: Compile and Ruff-check every temporary script**

```bash
python -m py_compile \
  /tmp/source_readiness_collection_plugin.py \
  /tmp/source_readiness_baseline.py \
  /tmp/source_readiness_instrument_edit.py \
  /tmp/source_readiness_instrument_run.py \
  /tmp/source_readiness_mutations.py \
  /tmp/source_readiness_endpoint.py
uv run --extra dev ruff check \
  /tmp/source_readiness_collection_plugin.py \
  /tmp/source_readiness_baseline.py \
  /tmp/source_readiness_instrument_edit.py \
  /tmp/source_readiness_instrument_run.py \
  /tmp/source_readiness_mutations.py \
  /tmp/source_readiness_endpoint.py
uv run --extra dev ruff format --check \
  /tmp/source_readiness_collection_plugin.py \
  /tmp/source_readiness_baseline.py \
  /tmp/source_readiness_instrument_edit.py \
  /tmp/source_readiness_instrument_run.py \
  /tmp/source_readiness_mutations.py \
  /tmp/source_readiness_endpoint.py
```

Expected: all scripts compile and both Ruff commands pass without changes. Any formatter drift is a plan defect to fix before proceeding; do not weaken checks or alter script semantics or exact match-once strings.

- [ ] **Step 4: Run the complete Block D matrix**

Run the exact `--all` aggregate command from Block D. Expected:

- exactly 41 recipes run with category counts `18/5/4/14`;
- final source admission, original completion, post-save 401, all three rights, proof deadline, save-before-transport, anchor/sample/session/row/effect deadlines, uncertainty, retained context, and sample/row/effect retry pins all report `intended-red`;
- both retry rows fail specifically for the isolated effect drop;
- timing-only and broad fence faults remain separate, and deleting the timing comparison is killed at its exact sentinel;
- every selected JUnit testcase independently matches the intended boundary and lacks its category's forbidden bootstrap readiness/postcondition, competing-expiry, barrier/timeout, setup, and collection signatures;
- the save-before-transport row fails specifically at the fresh durable revision versus outgoing `x-fleet-revision` assertion, not at fixture bootstrap;
- valid-flow guard deletions remain separately classified;
- every edit restores exact bytes/hash/diff/status.

- [ ] **Step 5: Re-run permanent tests after all restoration**

```bash
uv run --no-sync python -m pytest tests/test_fleetsharing_source_admission.py -q -rs
uv run --no-sync python /tmp/source_readiness_instrument_run.py candidate
uv run --no-sync python /tmp/source_readiness_endpoint.py
git diff --exit-code -- wingman
git status --short
```

Expected: `120 passed`, exact candidate structural counts, all four 167-case orders pass, no production diff, and only intended results/test edits remain.

- [ ] **Step 6: Record assertion-level evidence and review**

Append one table row per mutation/fault/guard deletion: exact edit, exact selected permanent ID(s), literal failure assertion/regex, result class, target pre-probe SHA-256, and restoration result. Use `requesting-code-review` for an independent review of mutation isolation, selected IDs, competing deadline preconditions, session-current-cache injection, effect-only drop, masked/timeout rejection, and exact restoration. Resolve every valid finding and rerun the full matrix.

- [ ] **Step 7: Commit Task 3**

```bash
uv run --extra dev ruff check tests/test_fleetsharing_source_admission.py
uv run --extra dev ruff format --check tests/test_fleetsharing_source_admission.py
git diff --check
git add tests/test_fleetsharing_source_admission.py docs/ci-source-admission-readiness-bootstrap-results.md
git diff --cached --name-only
git commit -m "test: retain Fleet retry effect authority"
```

Expected staged paths: only the source-admission test and results ledger.

---

### Task 4: Complete the Local Endpoint and Results

**Files:**
- Modify: `docs/ci-source-admission-readiness-bootstrap-results.md`
- Verify: all four allowed paths and every protected path

**Interfaces:**
- Consumes: Tasks 1–3 implementation, structural evidence, mutation logs, and exact endpoint scripts.
- Produces: complete local evidence for unchanged source 120/full 16609/three-file 167 identities, full suite `16595 + 14`, independent tool gates, scope, and restoration.

- [ ] **Step 1: Rebuild and install mandatory local prerequisites**

```bash
uv sync --locked --extra dev
node --version
cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available(), 'Native integration tests require the built codec'"
```

Expected: Node prints a version; release codec builds/copies; `codec.codec_available()` passes.

- [ ] **Step 2: Run exact source and three-file verification**

```bash
uv run --no-sync python -m pytest tests/test_fleetsharing_source_admission.py \
  -q -rs --durations=30 --junitxml=/tmp/source-readiness-final-120.xml
uv run --no-sync python /tmp/source_readiness_endpoint.py
uv run --no-sync python /tmp/source_readiness_instrument_run.py candidate
```

Expected: source 120 unchanged; all four 167 orders green; candidate structural counts exact; no skips.

- [ ] **Step 3: Run the relevant Fleet subsystem selection**

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_source_admission.py \
  tests/test_fleetsharing_remote_worker.py \
  tests/test_fleetsharing_worker_fix1.py \
  tests/test_fleetsharing_worker.py \
  tests/test_fleetsharing_worker_timing.py \
  tests/test_fleetsharing_worker_revision.py \
  tests/test_fleetsharing_state.py \
  tests/test_fleetsharing_state4.py \
  tests/test_fleetsharing_timing.py \
  tests/test_fleetsharing_timing_publisher.py \
  tests/test_fleetsharing_client.py \
  tests/test_fleetsharing_scheduling.py \
  tests/test_fleetsharing_crypto.py \
  -q -rs --durations=50 --junitxml=/tmp/source-readiness-fleet.xml
```

Expected: all selected tests pass; inspect and record any intentional platform skips.

- [ ] **Step 4: Run the complete suite and summarize exact identities**

```bash
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/source-readiness-full.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/source-readiness-full.xml /tmp/source-readiness-full.json
```

Expected: exactly `16595 passed, 14 skipped`; summary `case_count` exactly `16609`; source file exactly 120 cases; no Node/codec/unexpected native availability skip. Compare JUnit ordered identities byte-for-text with `/tmp/wingman-source-readiness-baseline/complete-16609.txt`.

- [ ] **Step 5: Run independent JS/Cargo/Ruff/diff gates**

```bash
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
git diff --check f6e8ecd5..HEAD
```

Expected: JS prints `PASS every page module loaded`; Cargo `1 passed; 0 failed`; Ruff passes; diff check prints nothing.

- [ ] **Step 6: Audit exact four-path scope and protected paths**

```bash
python - <<'PY'
import subprocess
expected = {
    "docs/superpowers/specs/2026-09-25-source-admission-readiness-bootstrap-design.md",
    "docs/superpowers/plans/2026-09-25-source-admission-readiness-bootstrap.md",
    "docs/ci-source-admission-readiness-bootstrap-results.md",
    "tests/test_fleetsharing_source_admission.py",
}
actual = set(subprocess.check_output(
    ["git", "diff", "--name-only", "f6e8ecd5..HEAD", "--", "."],
    text=True,
).splitlines())
assert actual == expected, sorted(actual ^ expected)
print(sorted(actual))
PY
git diff --exit-code f6e8ecd5..HEAD -- wingman .github pyproject.toml uv.lock packaging
git diff --exit-code f6e8ecd5..HEAD -- \
  tests/test_fleetsharing_remote_worker.py \
  tests/test_fleetsharing_worker_fix1.py
```

Expected: exact four paths; protected commands print no diff.

- [ ] **Step 7: Re-run the full mutation/restoration matrix from the final tree**

Run the complete Block D command again, then:

```bash
git diff --check
git diff --exit-code -- wingman
git status --short
```

Expected: every qualification result repeats; no mutation remains; only the results ledger may be uncommitted.

- [ ] **Step 8: Complete the local results document**

Record exact focused/subsystem/full commands and outcomes, 14 skip tuples, complete identity equality, source/three-file timing observations, structural counts, mutation/fault tables, four-path scope, and restoration. State explicitly:

```text
LOCAL CONCLUSION: the implementation preserves every source-admission and complete-suite identity while reducing real fixture bootstrap turns and saves to the approved structural counts. Local and hosted timings are observations only; no speedup is claimed.
```

- [ ] **Step 9: Run local self-review and independent review**

Self-review the spec checklist: scope, identities, interface, predicate, postconditions, six original-phase IDs, deadline independence, structural arithmetic, lifecycle seams, retry pins, qualification quality, order independence, claim discipline, and leftovers. Then use `requesting-code-review` for one independent review of the full `f6e8ecd5..HEAD` diff, results ledger, JUnit/timing JSON, mutation logs, and all scripts. Resolve findings and rerun affected verification.

- [ ] **Step 10: Commit the complete local results**

```bash
git add docs/ci-source-admission-readiness-bootstrap-results.md
git diff --cached --name-only
git commit -m "docs: record source admission readiness verification"
```

Expected staged path: only the results ledger.

---

### Task 5: Polish, Final Review, Publication Stop, and Authorized Hosted Comparison

**Files:**
- Modify only within the exact four-path tranche if polish/review requires changes: approved spec, this plan, results ledger, and source-admission test
- Review and commit: exact four allowed paths, including any executable polish
- Hosted read: an explicitly authorized run/PR bound to the frozen reviewed SHA only

**Interfaces:**
- Consumes: Task 4 locally verified four-path tranche.
- Produces: polished/final-reviewed changes committed inside the exact four paths, a clean worktree and frozen reviewed executable SHA, reviewer-facing explanation, explicit publication stop, and—only after separate authorization naming that SHA—hosted exact-identity comparison to PR #289.

- [ ] **Step 1: Run `polish-core --fix` and inspect every edit**

Use the `polish-core` skill with `--fix` against `f6e8ecd5..HEAD`. Accept only high-confidence changes within the four-path scope. Reject any production, caller, workflow, dependency, configuration, marker, selector, budget, shard, or fifth-path edit.

- [ ] **Step 2: Run fresh verification after polish**

At minimum rerun:

```bash
uv run --no-sync python -m pytest tests/test_fleetsharing_source_admission.py -q -rs
uv run --no-sync python /tmp/source_readiness_endpoint.py
uv run --no-sync python /tmp/source_readiness_instrument_run.py candidate
uv run --extra dev ruff check tests/test_fleetsharing_source_admission.py
uv run --extra dev ruff format --check tests/test_fleetsharing_source_admission.py
git diff --check
git diff --cached --check
git diff --check f6e8ecd5..HEAD
```

If polish touched executable test code, rerun the complete Block D matrix and the full suite. Expected endpoint remains source 120, full 16609, three-file 167, structural `682/921/802/1409/119`, and exactly six original-phase IDs.

- [ ] **Step 3: Run final independent review**

Use `requesting-code-review` against the approved spec, this plan, full diff, final results ledger, local JUnit/timing evidence, and mutation logs. Require explicit findings for predicate/fence fields, diagnostics, watch authority, durable equality, original phase, proof independence, retry keys/pins, mutation isolation/restoration, exact identities/orders, scope, and no-speedup claim. Resolve every valid finding and rerun affected checks.

- [ ] **Step 4: Run `change-explainer`**

Use the `change-explainer` skill and record a concise reviewer-facing section in the results ledger covering what changed, how readiness works, why six cases retain phase, how deadline/pin strength was qualified, exact verification, deviations (none unless recorded), edge cases, and reviewer focus.

- [ ] **Step 5: Record the publication stop in the committed ledger**

Add this exact text to the results ledger before the final local commit:

```text
PRE-AUTHORIZATION STOP: do not push, create or update a pull request, dispatch or rerun GitHub Actions, download a new-run artifact, or make a hosted acceptance claim until the maintainer explicitly authorizes publication of the verified executable head.
```

The current planning request authorizes none of those actions.

- [ ] **Step 6: Audit committed and uncommitted scope, commit polish, and freeze the reviewed SHA**

```bash
git status --short
git log --oneline f6e8ecd5..HEAD
git diff --stat f6e8ecd5..HEAD
git diff --check
git diff --cached --check
git diff --check f6e8ecd5..HEAD
python - <<'PY'
import subprocess

allowed = {
    "docs/superpowers/specs/2026-09-25-source-admission-readiness-bootstrap-design.md",
    "docs/superpowers/plans/2026-09-25-source-admission-readiness-bootstrap.md",
    "docs/ci-source-admission-readiness-bootstrap-results.md",
    "tests/test_fleetsharing_source_admission.py",
}

def paths(*args):
    return set(subprocess.check_output(args, text=True).splitlines())

committed = paths("git", "diff", "--name-only", "f6e8ecd5..HEAD", "--", ".")
unstaged = paths("git", "diff", "--name-only", "--", ".")
staged = paths("git", "diff", "--cached", "--name-only", "--", ".")
untracked = paths("git", "ls-files", "--others", "--exclude-standard")
uncommitted = unstaged | staged | untracked
assert committed | uncommitted == allowed, sorted((committed | uncommitted) ^ allowed)
assert uncommitted <= allowed, sorted(uncommitted - allowed)
print({"committed": sorted(committed), "uncommitted": sorted(uncommitted)})
PY
git add \
  docs/superpowers/specs/2026-09-25-source-admission-readiness-bootstrap-design.md \
  docs/superpowers/plans/2026-09-25-source-admission-readiness-bootstrap.md \
  docs/ci-source-admission-readiness-bootstrap-results.md \
  tests/test_fleetsharing_source_admission.py
python - <<'PY'
import subprocess
allowed = {
    "docs/superpowers/specs/2026-09-25-source-admission-readiness-bootstrap-design.md",
    "docs/superpowers/plans/2026-09-25-source-admission-readiness-bootstrap.md",
    "docs/ci-source-admission-readiness-bootstrap-results.md",
    "tests/test_fleetsharing_source_admission.py",
}
staged = set(subprocess.check_output(
    ["git", "diff", "--cached", "--name-only", "--", "."],
    text=True,
).splitlines())
assert staged and staged <= allowed, sorted(staged - allowed)
print(sorted(staged))
PY
git commit -m "test: finalize source admission readiness verification"
test -z "$(git status --porcelain=v2 --untracked-files=all)"
git diff --exit-code
git diff --cached --exit-code
REVIEWED_HEAD=$(git rev-parse HEAD)
case "$REVIEWED_HEAD" in
  ""|*[!0-9a-f]*) exit 1 ;;
esac
test "${#REVIEWED_HEAD}" -eq 40
printf 'REVIEWED_HEAD=%s\n' "$REVIEWED_HEAD"
```

Expected: the pre-commit uncommitted union is a subset of the exact four paths; every polish/executable/docs change is committed; the post-commit tree, index, and untracked inventory are clean; `f6e8ecd5..HEAD` is exactly the four allowed paths; and the printed 40-character `REVIEWED_HEAD` is the frozen reviewed executable head used by every later publication and hosted check.

- [ ] **Step 7: Obey the publication stop**

Stop after reporting the frozen `REVIEWED_HEAD`. Do not push, create/update a PR, dispatch/rerun Actions, download new-run artifacts, or claim hosted acceptance. Separate authorization must identify this exact reviewed SHA; authorization for another SHA does not transfer.

- [ ] **Step 8: Only after separate authorization, verify PR state and frozen-head binding before publication**

Run `gh pr view` and `git log` as required by repository policy. Confirm the PR targets `elboaf/FlyGD-Wingman` `main`, the local tree is still clean at the literal authorized `REVIEWED_HEAD`, the PR/run will use that exact executable head, and no reviewed PR is already merged. Never use `--no-verify`.

- [ ] **Step 9: Collect the explicitly authorized hosted run**

Materialize/compile/Ruff-check Block F, enter the literal frozen `REVIEWED_HEAD` plus the authorized run and PR numbers, and execute it once. The collector must reject any local, PR, run, job, checkout-log, or artifact head that does not equal the frozen reviewed SHA. Do not infer latest and do not rerun a failed order or artifact audit to green without recording the failed attempt.

- [ ] **Step 10: Update hosted evidence without a speedup claim**

Append exact run/attempt/attempt history, PR, synthetic/head/base, jobs, artifacts/digests, path scope, complete/source/three-file hashes and counts, normalized skips, source/three-file/job/Test-step timings, and structural local counts. State exact identity changes `+0/0` and this conclusion only:

```text
HOSTED CONCLUSION: the candidate preserves the exact PR #289 source-admission and complete-suite identities and normalized skips on both platforms. Structural turns/saves/loads match the approved local instrumentation. Hosted durations are single-run observations only; no speedup is claimed.
```

- [ ] **Step 11: Commit hosted evidence, then stop again unless separately authorized**

```bash
git add docs/ci-source-admission-readiness-bootstrap-results.md
git commit -m "docs: record hosted source admission readiness evidence"
```

Do not push this evidence head unless a second explicit authorization covers it. If pushed, verify all three required checks on the documentation head and record their literal URLs/conclusions before final completion.

- [ ] **Step 12: Final completion report**

Return:

- exact plan, implementation, local-evidence, frozen reviewed executable, hosted-evidence (if authorized), and final commit SHAs/subjects;
- every focused/order/subsystem/full/tool/mutation/hosted command actually run and literal outcome;
- exact source 120/full 16609/three-file 167 identity results and skip comparisons;
- exact `1428 -> 682`, `1469 -> 921`, `1350 -> 802`, `1928 -> 1409`, `0 -> 119` structural evidence;
- exact four committed paths, pre-commit uncommitted-scope audit, clean-tree proof, frozen `REVIEWED_HEAD`, and hosted head binding;
- no-speedup conclusion;
- remaining concerns: private-field coupling is intentional test authority, hosted timing is noisy/single-sample, and valid-flow guard deletions are non-discriminating but retained for diagnostics/postconditions.

## Stop Conditions

Stop and return to design review rather than adapting silently if:

1. any default rig needs more than 12 turns;
2. a seventh identity appears to need `original_phase=True`;
3. any of the first four phase identities changes exact body/timestamp;
4. readiness needs `_work()`, `_publication()`, planning inspection, sleeps, fallback drive, node ID, or call stack;
5. any common postcondition fails at first readiness;
6. watch readiness cannot prove both source and automatic accepted/status identities;
7. structural counts differ from `682/921/802/1409/119` or categories differ from `105/4/9/1`;
8. source 120, three-file 167, or complete 16609 identities/order/signatures/markers change;
9. an intended production/fault mutation fails only during bootstrap, another deadline, generic later refusal, collection/setup, barrier wait, or timeout;
10. isolated effect-drop does not fail both retry identities at exact effect key/cardinality/identity strength;
11. restoration cannot reproduce bytes/hash/binary diff/NUL status;
12. Node, codec, or unexpected native availability skips appear;
13. implementation requires any production, workflow, dependency, configuration, packaging, marker, selector, budget, shard, caller, helper, persistent harness, generated evidence, cached/shared fixture, in-memory store, private-state seed, or fifth-path change;
14. hosted identity/skips differ from PR #289;
15. evidence supports only elapsed-time attribution rather than the approved structural work claim.

## Plan Self-Review Checklist

Before committing this plan, verify:

- all approved spec sections map to Tasks 1–5;
- exact field names, helper signature, predicate, diagnostics, postconditions, call expressions, deadline preconditions, retry keys, and pin assertions are executable snippets;
- exact source/full/three-file hashes and counts are consistent across baseline, endpoint, and hosted blocks;
- baseline and candidate structural scripts instrument real `s.save`, real worker delegates, and real `drive`, and restore exactly;
- mutation catalog uses exact match-once edits, exact permanent IDs, intended regexes, masked/timeout rejection, aggregate reporting, and fatal restoration handling;
- valid-flow guard deletions are not misreported as kills;
- local prerequisites/full suite/JS/Cargo/Ruff/scope commands and expected outputs are explicit;
- hosted collector is explicit-input, rerun-aware, logs-primary, empty-PR-metadata-safe, artifact-time-windowed, identity/skip exact, and four-path scoped;
- no unresolved placeholder or estimated result remains;
- no speedup claim appears.
