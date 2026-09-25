# Windows Resource Memory Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Fleet maximum-response subprocess's Windows `tracemalloc` observation with a fail-closed native `K32GetProcessMemoryInfo` peak-working-set probe while preserving the exact maximum transport contract, six-property JUnit schema, non-Windows behavior, and test inventory except for two approved ordinary identities.

**Architecture:** Keep all instrumentation private to `tests/test_fleetsharing_transport_resources.py`. Select Windows before any `resource` or tracing fallback, lazily bind `GetCurrentProcess` and `K32GetProcessMemoryInfo`, sample a fresh naturally aligned `PROCESS_MEMORY_COUNTERS`, guard externally active tracing before the client decode, and wrap the exact protocol decoder/parser attributes only for the measured operation with unconditional identity restoration. The parent process immediately rejects a Windows child reporting any metric other than `process_peak_working_set_bytes` before budget evaluation or JUnit publication.

**Tech Stack:** Python 3.11, pytest, stdlib `ctypes`/`subprocess`/`tracemalloc`/`resource`/`xml.etree.ElementTree`, existing Fleet signed client and protocol codecs, existing JUnit timing summarizer, Node.js smoke harness, Cargo settings codec, uv, Git, and GitHub Actions artifacts.

**Spec:** `docs/superpowers/specs/2026-09-24-windows-resource-memory-probe-design.md`

## Global Constraints

- Source baseline is merged `main` commit `cc48c887ac3a140a2baf87d4bdcc3f6e916c02c9` (`Optimize setup controller fixture construction (#288)`).
- PR #288 executable evidence is run `36051546735`, attempt `1`, synthetic merge `515c6185789fc0c67c8cd6247f57569bc8a45076`, executable head `9d60c726dbe0d74263e59d865723e9575831f7a9`, and base `c23788e392bcd586dfc95b7390eaee18cb4ec224`.
- Preserve the original three target IDs byte-for-text and in their original order. Append exactly these two non-parameterized ordinary IDs, in this exact suffix order:
  1. `tests/test_fleetsharing_transport_resources.py::test_windows_memory_probe_reports_peak_working_set_without_tracing`
  2. `tests/test_fleetsharing_transport_resources.py::test_windows_memory_probe_fails_closed_and_restores_crossings`
- Target inventory changes exactly `3 -> 5`: four ordinary identities and one unchanged `resource` identity. Complete collection changes exactly `16,607 -> 16,609`, with two additions and zero removals, renames, reorderings, or parameterized suffixes.
- The sole `resource` identity remains `tests/test_fleetsharing_transport_resources.py::test_maximum_legal_response_actual_reader_and_codec_in_subprocess`.
- Preserve the maximum contract: 47,022,137 raw bytes, 8,192 rows, 155,648 observations, `read(67_108_865)`, response closure, real signed client, real response reader, real wire decoder, real DTO parser, child subprocess, 300-second subprocess timeout, 75-second wall budget, and six existing JUnit resource properties.
- Windows reports only `process_peak_working_set_bytes` from `PeakWorkingSetSize`. It never reports current working set, pagefile usage, traced allocations, a delta, or a memory ceiling.
- macOS with `resource` keeps `process_peak_rss_bytes`; Linux and other `resource` platforms keep `process_peak_rss_kib`; generic non-Windows without `resource` keeps `traced_peak_bytes`.
- Windows native load, named-export lookup, or API-call failure is loud. No Windows fallback to `resource` or `tracemalloc` is permitted.
- A pre-existing Windows tracer fails at the first line of `measure_response()`, before payload construction, native setup, sampling, or decode, and is never stopped. Accepted Windows execution calls neither `tracemalloc.start()` nor `tracemalloc.stop()`.
- Ordinary native tests install `_TraceSeam` as the actual `sys.modules["tracemalloc"]` entry throughout native setup, guard, repeated sampling, and test cleanup. The seam records `is_tracing()`, `start()`, and `stop()`; mutations that perform a real `import tracemalloc` cannot escape the witness.
- `ctypes.WinDLL`, `ctypes.get_last_error`, and `ctypes.WinError` are resolved only inside the selected Windows branch. Importing and running ordinary tests on Linux must not touch them.
- `PROCESS_MEMORY_COUNTERS` uses natural `ctypes.Structure` layout with no `_pack_`, exact ten fields/order, fixed-width `c_uint32` DWORDs, pointer-width `c_size_t` counters, and `c_void_p` handle signatures. Do not import or use `ctypes.wintypes`.
- The exact decoder and parser attributes are wrapped only during the injected measured operation; both originals are restored in `finally` by object identity. A failed operation re-raises the original exception object and makes no successful crossing-count claim.
- The parent Windows metric gate is the first executable validation after `json.loads(result.stdout)`. It precedes adding `subprocess_wall_seconds`, the 75-second budget assertion, every `record_property`, direct `user_properties` append, or equivalent publisher.
- A rejected Windows metric publishes zero `resource.*` properties.
- The six JUnit property names remain unchanged: `resource.subprocess_wall_seconds`, `resource.memory_metric`, `resource.memory_peak`, `resource.raw_bytes`, `resource.rows`, and `resource.observations`.
- No production, workflow, summarizer, timing-test, dependency, lockfile, packaging, configuration, marker, selector, timeout, budget, shard, product, or historical-document change is authorized.
- In particular, do not modify `tests/test_ci_timing.py`, `scripts/summarize_pytest_junit.py`, `.github/workflows/ci.yml`, any file under `wingman/`, `pyproject.toml`, or `uv.lock`.
- Exact committed tranche scope is limited to these five paths:
  - `docs/superpowers/specs/2026-09-24-windows-resource-memory-probe-design.md`
  - `docs/superpowers/plans/2026-09-24-windows-resource-memory-probe.md`
  - `docs/ci-windows-resource-memory-probe-results.md`
  - `docs/ci-test-budget-redesign.md`
  - `tests/test_fleetsharing_transport_resources.py`
- The structural claim is only: under the accepted environment, the maximum Windows Fleet response decode no longer starts or uses test-owned `tracemalloc`; externally active tracing fails before decode and is not stopped.
- Do not claim a case, suite, job, runner, critical-path, or overall speedup; do not compare native peak working set numerically with the earlier traced-allocation peak.
- Each task receives a fresh independent review against the spec and this plan. Record findings and fixes in the results ledger before the task commit.
- Temporary mutants are never committed. Every mutation probe captures pre-probe target bytes, SHA-256, `git diff --binary HEAD -- .`, and NUL-delimited porcelain-v2 status; restoration must reproduce all four exactly. The aggregate runner executes every requested recipe, records every command/regex failure, and exits nonzero if any recipe fails; an unsafe restoration failure stops subsequent mutation.
- Stop and return to design review if implementation needs a sixth path, more than two identities, any existing identity change, a Windows fallback, a metric/schema/budget change, a production/workflow/dependency edit, or weakening of any maximum-response boundary.

## File Structure and Ownership

- Create `docs/ci-windows-resource-memory-probe-results.md` as the sole evidence ledger for baseline identities, PR #288 provenance/artifacts/skips, TDD red/green results, mutation qualification, local endpoint, self-review, hosted acceptance, scope, and concerns.
- Modify `tests/test_fleetsharing_transport_resources.py` only for the native structure/binding, platform seams, trace guard, crossing helper, two appended tests, measured-operation integration, and immediate parent metric gate.
- Modify only the current-state paragraph under `### Transport resources` in `docs/ci-test-budget-redesign.md`; retain the historical 44.6-second row and every other section unchanged.
- Read but do not modify `wingman/fleetsharing/client.py` and `wingman/fleetsharing/protocol.py`. Temporary maximum-contract mutants may touch `client.py`, but the mutation runner restores exact bytes/diff/status before returning.
- Read but do not modify `tests/test_ci_timing.py`, `scripts/summarize_pytest_junit.py`, and `.github/workflows/ci.yml`; their unchanged behavior is acceptance evidence.

## Review-Risk Decisions

1. **ABI correctness:** natural structure layout, pointer widths, signatures, pseudo-handle ownership, fresh structures, exact `cb`, and immediate saved-error capture are pinned by a portable fake-DLL test and real hosted Windows execution.
2. **Measurement class:** Windows selection occurs before `resource`; there is no fallback. `PeakWorkingSetSize` is an absolute process-lifetime high-water mark, not current memory or decode allocation.
3. **Tracing ownership:** the child refuses externally active tracing before decode rather than stopping an external owner or mixing native evidence with Python tracing.
4. **Crossing proof:** exact-one decoder/parser counters reject bypass and duplication independently of output cardinality. `finally` restoration and sentinel identity are proved without another 47 MB execution.
5. **Evidence publication:** the parent metric gate runs immediately after JSON parse and rejects wrong Windows evidence before all six properties and before the wall budget.
6. **Compatibility:** all Windows symbols remain lazy so Linux ordinary tests can execute the Windows branch entirely through injected callables.
7. **Claim discipline:** hosted timing is observational only; the accepted conclusion is the structural instrumentation change.

## Task Right-Sizing

1. Task 1 freezes the merged PR #288 executable baseline and creates the results ledger without executable changes.
2. Task 2 adds the native success/ABI contract and first exact suffix identity, then independently qualifies branch, value, layout, signature, and no-tracing sensitivity.
3. Task 3 adds fail-closed behavior, tracing ownership, crossing restoration/counting, parent publication ordering, the second exact suffix identity, and the current budget-design paragraph.
4. Task 4 proves the complete local endpoint, full maximum subprocess, generic summarizer behavior, complete suite, skip inventory, tools, and exact scope/restoration.
5. Task 5 performs polish, final independent review, change explanation, an explicit publication stop, and—only after authorization—hosted Windows/Ubuntu acceptance plus evidence-head/final-head checks.

---

## Reproducibility Block A — merged baseline and PR #288 artifact audit

This block is run in Task 1. It extracts `cc48c887` to a disposable directory, collects source identities with a plugin, verifies the one resource owner, parses the existing PR #288 artifacts, checks JUnit/timing agreement, normalizes only pytest temporary-root fragments in skips, independently reparses logs-primary synthetic/head/base from all three checkout logs, and verifies extracted JUnit/timing bytes equal the corresponding ZIP members when both forms exist. It emits machine-readable evidence plus Markdown appendices and writes only under `/tmp`.

```bash
cat > /tmp/windows_memory_baseline_plugin.py <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path


def pytest_collection_finish(session):
    rows = [
        {
            "nodeid": item.nodeid,
            "resource": item.get_closest_marker("resource") is not None,
        }
        for item in session.items
    ]
    Path(os.environ["WINGMAN_COLLECTION_OUT"]).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
PY
cat > /tmp/windows_memory_baseline.py <<'PY'
from __future__ import annotations

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
from collections import defaultdict
from pathlib import Path

W = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-resource-memory-probe")
P = Path(sys.executable)
ART = Path(
    os.environ.get("PR288_ARTIFACT_ROOT", "/tmp/wingman-setup-hosted-36051546735")
)
OUTPUT = Path("/tmp/wingman-windows-memory-baseline")
BASE = "cc48c887ac3a140a2baf87d4bdcc3f6e916c02c9"
TARGET = "tests/test_fleetsharing_transport_resources.py"
TARGET_IDS = [
    TARGET + "::test_maximum_put_uses_actual_default_escaping_under_512k",
    TARGET + "::test_memory_probe_falls_back_without_resource",
    TARGET + "::test_maximum_legal_response_actual_reader_and_codec_in_subprocess",
]
RESOURCE_ID = TARGET_IDS[-1]


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
        WINGMAN_COLLECTION_OUT=str(output),
    )
    run = subprocess.run(
        [
            str(P),
            "-m",
            "pytest",
            *args,
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "windows_memory_baseline_plugin",
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
        "pytest-of-<USER>/pytest-<N>/<PYTEST_TMP>",
        text.replace("\\", "/"),
    )


def parse_artifact(platform: str) -> dict[str, object]:
    root = ART / "artifacts" / platform
    archive = ART / "artifacts" / f"{platform}.zip"
    if not (root / "pytest-result.xml").is_file():
        assert archive.is_file(), (platform, root, archive)
        root = OUTPUT / "extracted-artifacts" / platform
        root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as package:
            package.extractall(root)
    xml_path = root / "pytest-result.xml"
    timing_path = root / "pytest-timing.json"
    if archive.is_file() and (ART / "artifacts" / platform).is_dir():
        with zipfile.ZipFile(archive) as package:
            assert set(package.namelist()) == {
                "pytest-result.xml",
                "pytest-timing.json",
            }
            assert package.read("pytest-result.xml") == xml_path.read_bytes()
            assert package.read("pytest-timing.json") == timing_path.read_bytes()
    cases = list(ET.parse(xml_path).getroot().iter("testcase"))
    ids = [identity(case) for case in cases]
    assert len(ids) == len(set(ids)) == 16607
    counts: defaultdict[str, int] = defaultdict(int)
    seconds: defaultdict[str, float] = defaultdict(float)
    skips: list[tuple[str, str]] = []
    target_rows = []
    failures = errors = 0
    for node, case in zip(ids, cases, strict=True):
        duration = float(case.get("time", "0") or 0)
        file_name = node.split("::", 1)[0]
        counts[file_name] += 1
        seconds[file_name] += duration
        skipped = case.find("skipped")
        if skipped is not None:
            skips.append(
                (
                    node,
                    normalized_skip(skipped.get("message") or skipped.text or ""),
                )
            )
        failures += len(case.findall("failure"))
        errors += len(case.findall("error"))
        if file_name == TARGET:
            target_rows.append(
                {
                    "nodeid": node,
                    "seconds": duration,
                    "properties": {
                        prop.get("name", ""): prop.get("value", "")
                        for prop in case.findall("./properties/property")
                        if prop.get("name", "").startswith("resource.")
                    },
                }
            )
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    assert timing["case_count"] == len(ids)
    for file_name, row in timing["files"].items():
        assert row["cases"] == counts[file_name]
        assert abs(row["seconds"] - seconds[file_name]) < 1e-9
    assert failures == errors == 0
    assert [row["nodeid"] for row in target_rows] == TARGET_IDS
    expected_skips = {"ubuntu": 14, "windows": 67}[platform]
    assert len(skips) == expected_skips
    return {
        "case_count": len(ids),
        "complete_sha256": nodes_digest(ids),
        "target": target_rows,
        "target_seconds": seconds[TARGET],
        "skips": skips,
        "passed": len(ids) - len(skips),
        "xml_sha256": digest(xml_path.read_bytes()),
        "timing_sha256": digest(timing_path.read_bytes()),
        "archive_sha256": digest(archive.read_bytes()) if archive.is_file() else None,
    }


OUTPUT.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(
    prefix="wingman-windows-memory-baseline-"
) as directory:
    root = Path(directory)
    extract(BASE, root)
    target_rows = collect(root, [TARGET], OUTPUT / "target-collection.json")
    complete_rows = collect(root, ["tests"], OUTPUT / "complete-collection.json")
target_ids = [str(row["nodeid"]) for row in target_rows]
complete_ids = [str(row["nodeid"]) for row in complete_rows]
assert target_ids == TARGET_IDS
assert len(complete_ids) == len(set(complete_ids)) == 16607
assert [str(row["nodeid"]) for row in target_rows if row["resource"]] == [RESOURCE_ID]
assert sum(bool(row["resource"]) for row in complete_rows) == 1
source = {
    "target_count": len(target_ids),
    "target_sha256": nodes_digest(target_ids),
    "complete_count": len(complete_ids),
    "complete_sha256": nodes_digest(complete_ids),
    "resource_id": RESOURCE_ID,
}
selected = json.loads((ART / "selected.json").read_text(encoding="utf-8"))
merge_pattern = re.compile(
    r"HEAD is now at (?P<short>[0-9a-f]{7,40}) Merge "
    r"(?P<head>[0-9a-f]{40}) into (?P<base>[0-9a-f]{40})"
)
full_pattern = re.compile(r"(?P<sha>[0-9a-f]{40})\s*$")


def checkout_evidence(path):
    lines = path.read_text(errors="replace").splitlines()
    merges = [match for line in lines if (match := merge_pattern.search(line))]
    commands = [
        index
        for index, line in enumerate(lines)
        if "[command]" in line and "log -1 --format=%H" in line
    ]
    assert len(merges) == len(commands) == 1, (path, merges, commands)
    full = full_pattern.search(lines[commands[0] + 1])
    assert full, (path, lines[commands[0] + 1])
    synthetic = full.group("sha")
    assert synthetic.startswith(merges[0].group("short"))
    return synthetic, merges[0].group("head"), merges[0].group("base")


log_provenance = {
    checkout_evidence(ART / "logs" / f"{role}.log")
    for role in ("checks", "ubuntu", "windows")
}
assert len(log_provenance) == 1
log_synthetic, log_head, log_base = log_provenance.pop()
assert selected["run_id"] == 36051546735
assert selected["run_attempt"] == 1
assert selected["synthetic_merge"] == "515c6185789fc0c67c8cd6247f57569bc8a45076"
assert selected["head"] == "9d60c726dbe0d74263e59d865723e9575831f7a9"
assert selected["base"] == "c23788e392bcd586dfc95b7390eaee18cb4ec224"
assert selected["run_pull_request_metadata"] == "absent"
assert (
    log_synthetic,
    log_head,
    log_base,
) == (
    selected["synthetic_merge"],
    selected["head"],
    selected["base"],
)
assert selected["jobs"]["checks"]["id"] == 107808061930
assert selected["jobs"]["ubuntu"]["id"] == 107808061903
assert selected["jobs"]["windows"]["id"] == 107808061529
assert selected["artifacts"]["ubuntu"]["id"] == 10830398935
assert selected["artifacts"]["windows"]["id"] == 10831516363
platforms = {name: parse_artifact(name) for name in ("ubuntu", "windows")}
for name in ("ubuntu", "windows"):
    if platforms[name]["archive_sha256"] is not None:
        assert (
            "sha256:" + platforms[name]["archive_sha256"]
            == selected["artifacts"][name]["digest"]
        )
assert platforms["ubuntu"]["complete_sha256"] == source["complete_sha256"]
assert platforms["windows"]["complete_sha256"] == source["complete_sha256"]
assert platforms["ubuntu"]["target"][2]["properties"] == {
    "resource.subprocess_wall_seconds": "4.133140558999997",
    "resource.memory_metric": "process_peak_rss_kib",
    "resource.memory_peak": "455040",
    "resource.raw_bytes": "47022137",
    "resource.rows": "8192",
    "resource.observations": "155648",
}
assert platforms["windows"]["target"][2]["properties"] == {
    "resource.subprocess_wall_seconds": "45.94401130000006",
    "resource.memory_metric": "traced_peak_bytes",
    "resource.memory_peak": "282144272",
    "resource.raw_bytes": "47022137",
    "resource.rows": "8192",
    "resource.observations": "155648",
}
assert platforms["ubuntu"]["target"][2]["seconds"] == 4.134
assert platforms["windows"]["target"][2]["seconds"] == 45.946
summary = {
    "source": source,
    "provenance": {
        "run": selected["run_id"],
        "attempt": selected["run_attempt"],
        "synthetic": selected["synthetic_merge"],
        "head": selected["head"],
        "base": selected["base"],
        "run_pull_request_metadata": selected["run_pull_request_metadata"],
        "logs_primary": {
            "synthetic": log_synthetic,
            "head": log_head,
            "base": log_base,
        },
        "jobs": {role: selected["jobs"][role]["id"] for role in selected["jobs"]},
        "artifacts": {
            role: {
                "id": selected["artifacts"][role]["id"],
                "digest": selected["artifacts"][role]["digest"],
            }
            for role in ("ubuntu", "windows")
        },
    },
    "platforms": platforms,
}
(OUTPUT / "target-3.txt").write_text("\n".join(target_ids) + "\n", encoding="utf-8")
(OUTPUT / "complete-16607.txt").write_text(
    "\n".join(complete_ids) + "\n", encoding="utf-8"
)
for platform in ("ubuntu", "windows"):
    (OUTPUT / f"{platform}-skips.json").write_text(
        json.dumps(platforms[platform]["skips"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
(OUTPUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, sort_keys=True))
PY
python -m py_compile /tmp/windows_memory_baseline_plugin.py /tmp/windows_memory_baseline.py
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-windows-resource-memory-probe
uv run --extra dev python /tmp/windows_memory_baseline.py
```

Expected literal endpoint: target count `3`, complete count `16607`, exactly one resource owner, zero failures/errors, Ubuntu `16593 passed + 14 skipped`, Windows `16540 passed + 67 skipped`, Ubuntu resource `process_peak_rss_kib=455040` with child wall `4.133140558999997` and testcase `4.134`, Windows resource `traced_peak_bytes=282144272` with child wall `45.94401130000006` and testcase `45.946`, all three logs yielding synthetic `515c6185789fc0c67c8cd6247f57569bc8a45076` / head `9d60c726dbe0d74263e59d865723e9575831f7a9` / base `c23788e392bcd586dfc95b7390eaee18cb4ec224`, ZIP-member byte equality, and the exact jobs/artifacts above.

---

## Intended Final Test-Module Interfaces

The implementation is incremental across Tasks 2 and 3, but the final code must use these exact names and signatures so the two tasks and mutation catalog agree.

### Imports, sentinel, native structure, and platform probe

Use these Ruff-formatted imports in the existing import group:

```python
import ctypes
import io
import json
import os
import subprocess
import sys
import time
```

Insert after the constants:

```python
_MISSING = object()


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_uint32),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _windows_memory_probe(*, win_dll=None, get_last_error=None, win_error=None):
    if win_dll is None:
        win_dll = ctypes.WinDLL
    kernel32 = win_dll("kernel32", use_last_error=True)
    get_current_process = kernel32.GetCurrentProcess
    get_process_memory_info = kernel32.K32GetProcessMemoryInfo
    get_current_process.argtypes = []
    get_current_process.restype = ctypes.c_void_p
    get_process_memory_info.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
        ctypes.c_uint32,
    ]
    get_process_memory_info.restype = ctypes.c_int
    if get_last_error is None:
        get_last_error = ctypes.get_last_error
    if win_error is None:
        win_error = ctypes.WinError
    structure_size = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)

    def sample():
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = structure_size
        process = get_current_process()
        if not get_process_memory_info(process, ctypes.byref(counters), structure_size):
            saved_error = get_last_error()
            raise win_error(saved_error)
        return int(counters.PeakWorkingSetSize)

    return "process_peak_working_set_bytes", sample


def memory_probe(
    *,
    platform=None,
    win_dll=None,
    get_last_error=None,
    win_error=None,
    resource_module=_MISSING,
    tracemalloc_module=_MISSING,
):
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        return _windows_memory_probe(
            win_dll=win_dll,
            get_last_error=get_last_error,
            win_error=win_error,
        )
    if resource_module is _MISSING:
        try:
            import resource as resource_module
        except ImportError:
            resource_module = None
    if resource_module is None:
        if tracemalloc_module is _MISSING:
            import tracemalloc as tracemalloc_module
        tracemalloc_module.start()
        return (
            "traced_peak_bytes",
            lambda: tracemalloc_module.get_traced_memory()[1],
        )
    unit = "bytes" if platform == "darwin" else "kib"
    return (
        f"process_peak_rss_{unit}",
        lambda: resource_module.getrusage(resource_module.RUSAGE_SELF).ru_maxrss,
    )
```

Task 2 may initially raise a direct `RuntimeError` on a zero native return so its success path remains TDD-scoped. Task 3 replaces that line with the exact saved-error pairing shown above before adding the failure identity.

### Tracing guard and crossing helper

Add `_require_untraced_windows_decode()` in Task 2 because the first identity and tracing mutations depend on it. Add `_measure_protocol_crossings()` in Task 3. Both final definitions are:

```python
def _require_untraced_windows_decode(*, platform=None, tracemalloc_module=None):
    platform = sys.platform if platform is None else platform
    if platform != "win32":
        return
    if tracemalloc_module is None:
        import tracemalloc as tracemalloc_module
    if tracemalloc_module.is_tracing():
        raise RuntimeError(
            "Windows maximum-response measurement requires tracemalloc to be disabled."
        )


def _measure_protocol_crossings(operation):
    original_decode = protocol.decode_wire_json
    original_parse = protocol.parse_snapshot
    calls = {"decode": 0, "parse": 0}

    def counted_decode(*args, **kwargs):
        calls["decode"] += 1
        return original_decode(*args, **kwargs)

    def counted_parse(*args, **kwargs):
        calls["parse"] += 1
        return original_parse(*args, **kwargs)

    protocol.decode_wire_json = counted_decode
    protocol.parse_snapshot = counted_parse
    try:
        result = operation()
    finally:
        protocol.decode_wire_json = original_decode
        protocol.parse_snapshot = original_parse
    return result, calls["decode"], calls["parse"]
```

### `measure_response()` integration

Make the trace guard the first executable line, so an externally traced child fails before constructing the 47 MB payload:

```python
def measure_response():
    _require_untraced_windows_decode()
    buffer = io.BytesIO()
```

Retain the remaining payload construction and transport headers unchanged. Replace the measurement/client section with:

```python
    metric, probe = memory_probe()
    before = probe()
    start = time.perf_counter()
    result, decode_calls, parse_calls = _measure_protocol_crossings(
        lambda: client.FleetRelayClient(
            "https://relay.example.test", transport=transport
        ).read_snapshot(
            session_id="A" * 43,
            private_key=bytes(32),
            revision=7,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    elapsed = time.perf_counter() - start
    peak = probe()
    assert result.server_time_ms == protocol.JS_SAFE_MAX
    assert len(result.rows) == LIMITS["get_rows"], "maximum row cardinality changed"
    assert (
        sum(len(effect.observations) for row in result.rows for effect in row.effects)
        == observations
    ), "maximum observation cardinality changed"
    assert responses[0].closed, "maximum response was not closed"
    assert responses[0].reads == [67_108_865], "maximum response read amount changed"
    assert decode_calls == 1, "wire decoder crossing count changed"
    assert parse_calls == 1, "snapshot parser crossing count changed"
```

Also change the existing raw assertion to carry an owned witness message without changing its value:

```python
    assert len(raw) == 47_022_137, "maximum raw payload size changed"
```

### Parent ordering

The exact parent ordering after the subprocess return-code assertion is:

```python
    evidence = json.loads(result.stdout)
    if evidence["platform"] == "win32":
        assert evidence["memory_metric"] == "process_peak_working_set_bytes"
    evidence["subprocess_wall_seconds"] = wall_seconds
    for name in (
        "subprocess_wall_seconds",
        "memory_metric",
        "memory_peak",
        "raw_bytes",
        "rows",
        "observations",
    ):
        request.node.user_properties.append((f"resource.{name}", str(evidence[name])))
    assert wall_seconds <= MAXIMUM_RESPONSE_RESOURCE_BUDGET_S, (
        "maximum response resource budget exceeded: "
        + json.dumps(evidence, sort_keys=True)
    )
```

No statement may appear between JSON parsing and the conditional metric gate.

### Portable fakes used by both appended identities

Append these Ruff-formatted support classes immediately before the two new suffix tests. `_ResourceSeam` is deliberately usable so a Windows-to-resource mutant reaches the exact metric assertion; `_WinErrorSeam` accepts any positional arguments, records them, and returns the preconstructed exception sentinel:

```python
class _FakeExport:
    def __init__(self, callback):
        self._callback = callback
        self.argtypes = None
        self.restype = None
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self._callback(*args)


class _FakeKernel32:
    def __init__(self, exports):
        self._exports = exports
        self.lookups = []

    def __getattr__(self, name):
        self.lookups.append(name)
        value = self._exports[name]
        if isinstance(value, BaseException):
            raise value
        return value


class _TraceSeam:
    def __init__(self, *, active=False):
        self.active = active
        self.is_tracing_calls = 0
        self.starts = 0
        self.stops = 0

    def is_tracing(self):
        self.is_tracing_calls += 1
        return self.active

    def start(self):
        self.starts += 1
        self.active = True

    def stop(self):
        self.stops += 1
        self.active = False

    def get_traced_memory(self):
        return (0, 0)


class _ResourceSeam:
    RUSAGE_SELF = object()

    def __init__(self):
        self.accesses = []

    def getrusage(self, who):
        self.accesses.append(who)
        return type("Usage", (), {"ru_maxrss": 123})()


class _WinErrorSeam:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result
```

### Exact first appended identity

```python
def test_windows_memory_probe_reports_peak_working_set_without_tracing(monkeypatch):
    pointer_size = ctypes.sizeof(ctypes.c_size_t)
    if pointer_size == 8:
        peaks = [(1 << 32) + 12_345, (1 << 32) + 67_890]
        currents = [345_678_901, 456_789_012]
        pagefiles = [234_567_890, 123_456_789]
    else:
        peaks = [0xF1234567, 0xE2345678]
        currents = [0x71234567, 0x62345678]
        pagefiles = [0x51234567, 0x42345678]
    pseudo_handle = 0xFFFF_FFFF
    structures = []
    samples = []

    def current_process():
        return pseudo_handle

    def memory_info(handle, counters_pointer, byte_size):
        counters = counters_pointer._obj
        sample_index = len(samples)
        structures.append(counters)
        samples.append(
            {
                "handle": handle,
                "cb": counters.cb,
                "byte_size": byte_size,
            }
        )
        counters.PeakWorkingSetSize = peaks[sample_index]
        counters.WorkingSetSize = currents[sample_index]
        counters.PagefileUsage = pagefiles[sample_index]
        counters.PeakPagefileUsage = pagefiles[sample_index] - 1
        return 1

    get_current_process = _FakeExport(current_process)
    get_process_memory_info = _FakeExport(memory_info)
    close_handle = _FakeExport(lambda _handle: 1)
    kernel32 = _FakeKernel32(
        {
            "GetCurrentProcess": get_current_process,
            "K32GetProcessMemoryInfo": get_process_memory_info,
            "CloseHandle": close_handle,
        }
    )
    loads = []

    def load_library(name, **kwargs):
        loads.append((name, kwargs))
        return kernel32

    tracing = _TraceSeam()
    resource = _ResourceSeam()
    monkeypatch.setitem(sys.modules, "tracemalloc", tracing)

    def unused_error_seam(*_args):
        raise AssertionError("success path consulted an error seam")

    metric, probe = memory_probe(
        platform="win32",
        win_dll=load_library,
        get_last_error=unused_error_seam,
        win_error=unused_error_seam,
        resource_module=resource,
    )
    _require_untraced_windows_decode(platform="win32")

    assert metric == "process_peak_working_set_bytes"
    assert loads == [("kernel32", {"use_last_error": True})]
    assert get_current_process.argtypes == []
    assert get_current_process.restype is ctypes.c_void_p
    assert get_process_memory_info.argtypes == [
        ctypes.c_void_p,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
        ctypes.c_uint32,
    ]
    assert get_process_memory_info.restype is ctypes.c_int
    assert PROCESS_MEMORY_COUNTERS._fields_ == [
        ("cb", ctypes.c_uint32),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]
    assert PROCESS_MEMORY_COUNTERS.cb.offset == 0
    assert PROCESS_MEMORY_COUNTERS.PageFaultCount.offset == 4
    pointer_fields = [
        "PeakWorkingSetSize",
        "WorkingSetSize",
        "QuotaPeakPagedPoolUsage",
        "QuotaPagedPoolUsage",
        "QuotaPeakNonPagedPoolUsage",
        "QuotaNonPagedPoolUsage",
        "PagefileUsage",
        "PeakPagefileUsage",
    ]
    assert [
        getattr(PROCESS_MEMORY_COUNTERS, name).offset for name in pointer_fields
    ] == [8 + index * pointer_size for index in range(8)]
    assert ctypes.sizeof(PROCESS_MEMORY_COUNTERS) == 8 + 8 * pointer_size
    assert ctypes.alignment(PROCESS_MEMORY_COUNTERS) == ctypes.alignment(
        ctypes.c_size_t
    )
    assert ctypes.alignment(PROCESS_MEMORY_COUNTERS) in (4, 8)
    assert not hasattr(PROCESS_MEMORY_COUNTERS, "_pack_")

    assert [probe(), probe()] == peaks
    assert close_handle.calls == []
    assert kernel32.lookups == ["GetCurrentProcess", "K32GetProcessMemoryInfo"]
    assert len(structures) == 2 and structures[0] is not structures[1]
    expected_size = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    assert samples == [
        {"handle": pseudo_handle, "cb": expected_size, "byte_size": expected_size},
        {"handle": pseudo_handle, "cb": expected_size, "byte_size": expected_size},
    ]
    assert resource.accesses == []
    assert tracing.is_tracing_calls == 1
    monkeypatch.undo()
    assert tracing.starts == tracing.stops == 0
```

### Exact second appended identity

```python
def test_windows_memory_probe_fails_closed_and_restores_crossings(monkeypatch):
    def assert_no_fallback(resource, tracing):
        assert resource.accesses == []
        assert tracing.starts == tracing.stops == 0

    def unexpected_last_error():
        raise AssertionError("native failure consulted last error too early")

    loader_error = OSError("kernel32 load failed")
    loader_win_error = _WinErrorSeam(OSError("unused loader WinError"))

    def failed_loader(_name, **_kwargs):
        raise loader_error

    resource = _ResourceSeam()
    tracing = _TraceSeam()
    monkeypatch.setitem(sys.modules, "tracemalloc", tracing)
    with pytest.raises(OSError) as caught:
        memory_probe(
            platform="win32",
            win_dll=failed_loader,
            get_last_error=unexpected_last_error,
            win_error=loader_win_error,
            resource_module=resource,
        )
    assert caught.value is loader_error
    assert loader_win_error.calls == []
    assert_no_fallback(resource, tracing)

    for missing_name in ("GetCurrentProcess", "K32GetProcessMemoryInfo"):
        missing_error = AttributeError(f"missing {missing_name}")
        exports = {
            "GetCurrentProcess": _FakeExport(lambda: 123),
            "K32GetProcessMemoryInfo": _FakeExport(lambda *_args: 1),
        }
        exports[missing_name] = missing_error
        kernel32 = _FakeKernel32(exports)
        resource = _ResourceSeam()
        tracing = _TraceSeam()
        named_win_error = _WinErrorSeam(OSError("unused named-export WinError"))
        monkeypatch.setitem(sys.modules, "tracemalloc", tracing)
        try:
            memory_probe(
                platform="win32",
                win_dll=lambda _name, **_kwargs: kernel32,
                get_last_error=unexpected_last_error,
                win_error=named_win_error,
                resource_module=resource,
            )
        except AttributeError as error:
            caught_error = error
        else:
            caught_error = None
        assert caught_error is missing_error
        assert kernel32.lookups[-1] == missing_name
        assert named_win_error.calls == []
        assert_no_fallback(resource, tracing)

    events = []
    saved_error = 1_234
    win_error_result = OSError("native memory query failed")

    def failed_memory_info(_handle, counters_pointer, _byte_size):
        events.append("api")
        counters_pointer._obj.PeakWorkingSetSize = 999_999
        counters_pointer._obj.WorkingSetSize = 888_888
        return 0

    def get_last_error():
        events.append("get_last_error")
        return saved_error

    kernel32 = _FakeKernel32(
        {
            "GetCurrentProcess": _FakeExport(lambda: 123),
            "K32GetProcessMemoryInfo": _FakeExport(failed_memory_info),
        }
    )
    resource = _ResourceSeam()
    tracing = _TraceSeam()
    win_error = _WinErrorSeam(win_error_result)
    monkeypatch.setitem(sys.modules, "tracemalloc", tracing)
    metric, probe = memory_probe(
        platform="win32",
        win_dll=lambda _name, **_kwargs: kernel32,
        get_last_error=get_last_error,
        win_error=win_error,
        resource_module=resource,
    )
    assert metric == "process_peak_working_set_bytes"
    with pytest.raises(OSError) as caught:
        probe()
    assert caught.value is win_error_result
    assert events == ["api", "get_last_error"]
    assert win_error.calls == [(saved_error,)]
    assert_no_fallback(resource, tracing)

    active_trace = _TraceSeam(active=True)
    monkeypatch.setitem(sys.modules, "tracemalloc", active_trace)
    with pytest.raises(RuntimeError, match="requires tracemalloc to be disabled"):
        _require_untraced_windows_decode(platform="win32")
    assert active_trace.active
    assert active_trace.is_tracing_calls == 1
    assert active_trace.starts == active_trace.stops == 0

    if sys.platform == "win32":
        child_command = [sys.executable, __file__, "--measure"]
    else:
        child_code = (
            "import json, runpy, sys; "
            f"sys.argv = [{__file__!r}, '--measure']; "
            f"scope = runpy.run_path({__file__!r}, run_name='memory_probe_child'); "
            "sys.platform = 'win32'; "
            "print(json.dumps(scope['measure_response']()))"
        )
        child_command = [sys.executable, "-c", child_code]
    child = subprocess.run(
        child_command,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONTRACEMALLOC": "1"},
    )
    assert child.returncode != 0
    assert child.stdout == ""
    assert "requires tracemalloc to be disabled" in child.stderr

    original_decode = protocol.decode_wire_json
    original_parse = protocol.parse_snapshot
    sentinel = RuntimeError("crossing sentinel")

    def failed_operation():
        decoded = protocol.decode_wire_json(
            b'{"protocol":2,"server_time_ms":0,"rows":[]}'
        )
        protocol.parse_snapshot(decoded)
        raise sentinel

    with pytest.raises(RuntimeError) as caught:
        _measure_protocol_crossings(failed_operation)
    assert caught.value is sentinel
    assert protocol.decode_wire_json is original_decode
    assert protocol.parse_snapshot is original_parse
    monkeypatch.undo()
    assert active_trace.active
    assert active_trace.starts == active_trace.stops == 0
```

### Existing fallback identity edit

Apply this adaptation in Task 2, before its GREEN run. Keep the existing name and behavior, but force the portable non-Windows branch:

```python
def test_memory_probe_falls_back_without_resource(monkeypatch):
    import tracemalloc

    monkeypatch.setitem(sys.modules, "resource", None)
    metric, probe = memory_probe(platform="linux")
    try:
        assert metric == "traced_peak_bytes"
        before = probe()
        allocation = bytearray(1024 * 1024)
        assert probe() >= before + len(allocation)
    finally:
        tracemalloc.stop()
```

---

## Reproducibility Block B1 — executable Task 2 interim identity/scope audit

Create this script before Task 2 qualification. It proves the exact ordered `16,608` inventory by inserting the first suffix immediately after the baseline target anchor, preserves every baseline ID in relative order, retains exactly one resource marker, hashes and writes the complete inventory, and requires the exact four-path Task 2 diff.

```bash
cat > /tmp/windows_memory_interim.py <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

W = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-resource-memory-probe")
P = Path(sys.executable)
B = Path("/tmp/wingman-windows-memory-baseline")
OUTPUT = Path("/tmp/wingman-windows-memory-interim")
TARGET = "tests/test_fleetsharing_transport_resources.py"
FIRST = TARGET + "::test_windows_memory_probe_reports_peak_working_set_without_tracing"
EXPECTED_PATHS = {
    "docs/superpowers/specs/2026-09-24-windows-resource-memory-probe-design.md",
    "docs/superpowers/plans/2026-09-24-windows-resource-memory-probe.md",
    "docs/ci-windows-resource-memory-probe-results.md",
    TARGET,
}


def digest(nodes):
    return hashlib.sha256(("\n".join(nodes) + "\n").encode()).hexdigest()


def collect(args, output):
    env = dict(os.environ, PYTHONPATH=f"{W}:/tmp", WINGMAN_COLLECTION_OUT=str(output))
    run = subprocess.run(
        [
            str(P),
            "-m",
            "pytest",
            *args,
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "windows_memory_baseline_plugin",
        ],
        cwd=W,
        env=env,
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(output.read_text(encoding="utf-8"))


OUTPUT.mkdir(exist_ok=True)
baseline_target = (B / "target-3.txt").read_text(encoding="utf-8").splitlines()
baseline_complete = (B / "complete-16607.txt").read_text(encoding="utf-8").splitlines()
target_rows = collect([TARGET], OUTPUT / "target.json")
complete_rows = collect(["tests"], OUTPUT / "complete.json")
target = [row["nodeid"] for row in target_rows]
complete = [row["nodeid"] for row in complete_rows]
anchor = baseline_complete.index(baseline_target[-1]) + 1
expected_complete = [*baseline_complete[:anchor], FIRST, *baseline_complete[anchor:]]
assert target == [*baseline_target, FIRST]
assert len(target) == len(set(target)) == 4
assert [row["nodeid"] for row in target_rows if row["resource"]] == [
    baseline_target[-1]
]
assert complete == expected_complete
assert len(complete) == len(set(complete)) == 16_608
assert [node for node in complete if node not in set(baseline_complete)] == [FIRST]
assert all(node in complete for node in baseline_complete)
assert sum(bool(row["resource"]) for row in complete_rows) == 1
changed = set(
    subprocess.check_output(
        ["git", "-C", str(W), "diff", "--name-only", "cc48c887", "--", "."],
        text=True,
    ).splitlines()
)
assert changed == EXPECTED_PATHS, sorted(changed ^ EXPECTED_PATHS)
summary = {
    "target_count": len(target),
    "target_sha256": digest(target),
    "complete_count": len(complete),
    "complete_sha256": digest(complete),
    "added": [FIRST],
    "removed": [],
    "resource_count": sum(bool(row["resource"]) for row in target_rows),
    "changed_paths": sorted(changed),
}
(OUTPUT / "target-4.txt").write_text("\n".join(target) + "\n", encoding="utf-8")
(OUTPUT / "complete-16608.txt").write_text("\n".join(complete) + "\n", encoding="utf-8")
(OUTPUT / "summary.json").write_text(
    json.dumps(summary, sort_keys=True, indent=2) + "\n"
)
print(json.dumps(summary, sort_keys=True))
PY
python -m py_compile /tmp/windows_memory_interim.py
```

Expected Task 2 endpoint: exact target order `baseline three + first suffix`, target `4`, complete `16,608`, additions/removals `+1/0`, resource markers `1`, and changed paths exactly spec, plan, results, and target test.

---

## Reproducibility Block B — exact endpoint identity/scope audit

Create this in Task 3 and rerun it in Tasks 4 and 5. It derives the exact complete order by inserting the two suffix IDs immediately after the baseline target anchor, preserves every baseline ID in relative order, hashes and writes the complete inventory, and refuses any suffix/order/count/scope drift.

```bash
cat > /tmp/windows_memory_endpoint.py <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

W = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-resource-memory-probe")
P = Path(sys.executable)
B = Path("/tmp/wingman-windows-memory-baseline")
OUTPUT = Path("/tmp/wingman-windows-memory-endpoint")
TARGET = "tests/test_fleetsharing_transport_resources.py"
SUFFIX = [
    TARGET + "::test_windows_memory_probe_reports_peak_working_set_without_tracing",
    TARGET + "::test_windows_memory_probe_fails_closed_and_restores_crossings",
]
EXPECTED_PATHS = {
    "docs/superpowers/specs/2026-09-24-windows-resource-memory-probe-design.md",
    "docs/superpowers/plans/2026-09-24-windows-resource-memory-probe.md",
    "docs/ci-windows-resource-memory-probe-results.md",
    "docs/ci-test-budget-redesign.md",
    TARGET,
}


def digest(nodes):
    return hashlib.sha256(("\n".join(nodes) + "\n").encode()).hexdigest()


def collect(args, output):
    env = dict(os.environ, PYTHONPATH=f"{W}:/tmp", WINGMAN_COLLECTION_OUT=str(output))
    run = subprocess.run(
        [
            str(P),
            "-m",
            "pytest",
            *args,
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "windows_memory_baseline_plugin",
        ],
        cwd=W,
        env=env,
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(output.read_text(encoding="utf-8"))


OUTPUT.mkdir(exist_ok=True)
baseline_target = (B / "target-3.txt").read_text(encoding="utf-8").splitlines()
baseline_complete = (B / "complete-16607.txt").read_text(encoding="utf-8").splitlines()
target_rows = collect([TARGET], OUTPUT / "target.json")
complete_rows = collect(["tests"], OUTPUT / "complete.json")
target = [row["nodeid"] for row in target_rows]
complete = [row["nodeid"] for row in complete_rows]
anchor = baseline_complete.index(baseline_target[-1]) + 1
expected_complete = baseline_complete[:anchor] + SUFFIX + baseline_complete[anchor:]
assert target == baseline_target + SUFFIX
assert len(target) == len(set(target)) == 5
assert [row["nodeid"] for row in target_rows if row["resource"]] == [
    baseline_target[-1]
]
assert complete == expected_complete
assert len(complete) == len(set(complete)) == 16_609
assert [node for node in complete if node not in set(baseline_complete)] == SUFFIX
assert all(node in complete for node in baseline_complete)
assert sum(bool(row["resource"]) for row in complete_rows) == 1
changed = set(
    subprocess.check_output(
        ["git", "-C", str(W), "diff", "--name-only", "cc48c887", "--", "."],
        text=True,
    ).splitlines()
)
assert changed == EXPECTED_PATHS, sorted(changed ^ EXPECTED_PATHS)
summary = {
    "target_count": len(target),
    "target_sha256": digest(target),
    "ordinary_count": sum(not row["resource"] for row in target_rows),
    "resource_count": sum(bool(row["resource"]) for row in target_rows),
    "complete_count": len(complete),
    "complete_sha256": digest(complete),
    "added": SUFFIX,
    "removed": [],
    "changed_paths": sorted(changed),
}
(OUTPUT / "target-5.txt").write_text("\n".join(target) + "\n", encoding="utf-8")
(OUTPUT / "complete-16609.txt").write_text("\n".join(complete) + "\n", encoding="utf-8")
(OUTPUT / "summary.json").write_text(
    json.dumps(summary, sort_keys=True, indent=2) + "\n"
)
print(json.dumps(summary, sort_keys=True))
PY
python -m py_compile /tmp/windows_memory_endpoint.py
```

Expected final endpoint: target `5`, ordinary `4`, resource `1`, complete `16609`, exact two-ID suffix, zero removals, and changed paths contained by the exact five-path allowlist.

---

## Reproducibility Block B3 — exact local JUnit, skip, inventory, and scope audit

Create this script in Task 4 after producing the named JUnit and timing files. It compares the full ordered inventory byte-for-byte with Block B, proves both new identities passed rather than skipped, compares normalized Linux skips with the exact Task 1 Ubuntu tuples, directly validates all six resource properties, cross-checks the generic timing summary, returns inventory hashes, and enforces the exact five-path set.

```bash
cat > /tmp/windows_memory_local_audit.py <<'PY'
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

W = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-resource-memory-probe")
B = Path("/tmp/wingman-windows-memory-baseline")
E = Path("/tmp/wingman-windows-memory-endpoint")
TARGET = "tests/test_fleetsharing_transport_resources.py"
NEW_IDS = [
    TARGET + "::test_windows_memory_probe_reports_peak_working_set_without_tracing",
    TARGET + "::test_windows_memory_probe_fails_closed_and_restores_crossings",
]
EXPECTED_PATHS = {
    "docs/superpowers/specs/2026-09-24-windows-resource-memory-probe-design.md",
    "docs/superpowers/plans/2026-09-24-windows-resource-memory-probe.md",
    "docs/ci-windows-resource-memory-probe-results.md",
    "docs/ci-test-budget-redesign.md",
    TARGET,
}
PROPERTY_NAMES = {
    "resource.subprocess_wall_seconds",
    "resource.memory_metric",
    "resource.memory_peak",
    "resource.raw_bytes",
    "resource.rows",
    "resource.observations",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(case):
    parts = case.get("classname", "").split(".")
    assert len(parts) >= 2 and parts[0] == "tests", parts
    return "::".join(("/".join(parts[:2]) + ".py", *parts[2:], case.get("name", "")))


def normalized_skip(text):
    return re.sub(
        r"pytest-of-[^/\s]+/pytest-\d+/[^\s:\"']+",
        "pytest-of-<USER>/pytest-<N>/<PYTEST_TMP>",
        text.replace("\\", "/"),
    )


def parse(path):
    cases = list(ET.parse(path).getroot().iter("testcase"))
    ids = [identity(case) for case in cases]
    assert len(ids) == len(set(ids))
    rows = []
    for node, case in zip(ids, cases, strict=True):
        skipped = case.find("skipped")
        failures = case.findall("failure")
        errors = case.findall("error")
        outcome = (
            "skipped"
            if skipped is not None
            else "failed"
            if failures or errors
            else "passed"
        )
        rows.append(
            {
                "nodeid": node,
                "outcome": outcome,
                "skip": None
                if skipped is None
                else normalized_skip(skipped.get("message") or skipped.text or ""),
                "properties": {
                    prop.get("name", ""): prop.get("value", "")
                    for prop in case.findall("./properties/property")
                    if prop.get("name", "").startswith("resource.")
                },
            }
        )
    return ids, rows


expected_complete = (E / "complete-16609.txt").read_text(encoding="utf-8").splitlines()
expected_target = (E / "target-5.txt").read_text(encoding="utf-8").splitlines()
baseline_skips = json.loads((B / "ubuntu-skips.json").read_text(encoding="utf-8"))
full_ids, full_rows = parse(Path("/tmp/windows-memory-full.xml"))
target_ids, target_rows = parse(Path("/tmp/windows-memory-target.xml"))
resource_ids, resource_rows = parse(Path("/tmp/windows-memory-resource-final.xml"))
assert full_ids == expected_complete
assert target_ids == expected_target
assert len(full_ids) == 16_609
assert all(row["outcome"] == "passed" for row in target_rows)
assert all(
    next(row for row in full_rows if row["nodeid"] == node)["outcome"] == "passed"
    for node in NEW_IDS
)
full_skips = [
    [row["nodeid"], row["skip"]] for row in full_rows if row["outcome"] == "skipped"
]
assert full_skips == baseline_skips
assert len(full_skips) == 14
assert sum(row["outcome"] == "passed" for row in full_rows) == 16_595
assert resource_ids == [
    TARGET + "::test_maximum_legal_response_actual_reader_and_codec_in_subprocess"
]
resource = resource_rows[0]
assert resource["outcome"] == "passed"
assert set(resource["properties"]) == PROPERTY_NAMES
assert resource["properties"]["resource.memory_metric"] == "process_peak_rss_kib"
assert resource["properties"]["resource.raw_bytes"] == "47022137"
assert resource["properties"]["resource.rows"] == "8192"
assert resource["properties"]["resource.observations"] == "155648"
assert int(resource["properties"]["resource.memory_peak"]) > 0
assert float(resource["properties"]["resource.subprocess_wall_seconds"]) <= 75
summary = json.loads(Path("/tmp/windows-memory-full.json").read_text(encoding="utf-8"))
assert summary["case_count"] == 16_609
assert len(summary["resource_evidence"]) == 1
assert set(summary["resource_evidence"][0]["properties"]) == PROPERTY_NAMES
changed = set(
    subprocess.check_output(
        ["git", "-C", str(W), "diff", "--name-only", "cc48c887", "--", "."],
        text=True,
    ).splitlines()
)
assert changed == EXPECTED_PATHS, sorted(changed ^ EXPECTED_PATHS)
report = {
    "complete_count": len(full_ids),
    "complete_sha256": digest(("\n".join(full_ids) + "\n").encode()),
    "target_count": len(target_ids),
    "target_sha256": digest(("\n".join(target_ids) + "\n").encode()),
    "passed": 16_595,
    "skips": full_skips,
    "new_passed": NEW_IDS,
    "resource_properties": resource["properties"],
    "changed_paths": sorted(changed),
}
Path("/tmp/windows-memory-local-audit.json").write_text(
    json.dumps(report, sort_keys=True, indent=2) + "\n"
)
print(json.dumps(report, sort_keys=True))
PY
python -m py_compile /tmp/windows_memory_local_audit.py
```

---

## Reproducibility Block C — restoration-safe mutation runner

Create and compile this runner in Task 2; its success/ABI subset matches the Task 2 source, and Task 3 enables the remaining recipes after adding the failure/crossing/resource code. Every catalog entry is exact match-once. The aggregate command runs all requested recipes even after ordinary command/regex failures, exits nonzero if any failed, and restores pre-probe bytes, SHA-256, binary diff, and porcelain-v2 status in `finally`. Product mutants are permitted only here and must leave no diff.

```bash
cat > /tmp/windows_memory_mutation.py <<'PY'
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

W = Path(
    os.environ.get(
        "WINDOWS_MEMORY_WORKTREE",
        "/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-resource-memory-probe",
    )
)
P = Path(sys.executable)
TEST = "tests/test_fleetsharing_transport_resources.py"
SUCCESS = TEST + "::test_windows_memory_probe_reports_peak_working_set_without_tracing"
FAILURE = TEST + "::test_windows_memory_probe_fails_closed_and_restores_crossings"
RESOURCE = TEST + "::test_maximum_legal_response_actual_reader_and_codec_in_subprocess"

MUTATIONS = {
    "windows-to-resource": {
        "target": TEST,
        "edits": [
            ('    if platform == "win32":\n', '    if platform == "never-win32":\n')
        ],
        "node": SUCCESS,
        "expect_regex": r'assert metric == "process_peak_working_set_bytes"',
    },
    "windows-to-tracing": {
        "target": TEST,
        "edits": [
            (
                "        return _windows_memory_probe(\n            win_dll=win_dll,\n            get_last_error=get_last_error,\n            win_error=win_error,\n        )\n",
                '        import tracemalloc\n        tracemalloc.start()\n        return "traced_peak_bytes", lambda: 0\n',
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"requires tracemalloc to be disabled",
    },
    "start-tracing": {
        "target": TEST,
        "edits": [
            (
                '    kernel32 = win_dll("kernel32", use_last_error=True)\n',
                '    import tracemalloc\n    tracemalloc.start()\n    kernel32 = win_dll("kernel32", use_last_error=True)\n',
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"requires tracemalloc to be disabled",
    },
    "stop-tracing": {
        "target": TEST,
        "edits": [
            (
                '    kernel32 = win_dll("kernel32", use_last_error=True)\n',
                '    import tracemalloc\n    tracemalloc.stop()\n    kernel32 = win_dll("kernel32", use_last_error=True)\n',
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"assert tracing.starts == tracing.stops == 0",
    },
    "current-working-set": {
        "target": TEST,
        "edits": [
            (
                "        return int(counters.PeakWorkingSetSize)\n",
                "        return int(counters.WorkingSetSize)\n",
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"assert \[probe\(\), probe\(\)\] == peaks",
    },
    "width-truncation": {
        "target": TEST,
        "edits": [
            (
                "        return int(counters.PeakWorkingSetSize)\n",
                "        return int(ctypes.c_uint32(counters.PeakWorkingSetSize).value)\n",
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"assert \[probe\(\), probe\(\)\] == peaks",
        "requires_pointer_size": 8,
    },
    "signed-coercion": {
        "target": TEST,
        "edits": [
            (
                "        return int(counters.PeakWorkingSetSize)\n",
                "        return int(ctypes.c_int32(counters.PeakWorkingSetSize).value)\n",
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"assert \[probe\(\), probe\(\)\] == peaks",
    },
    "wrong-native-metric": {
        "target": TEST,
        "edits": [
            (
                '    return "process_peak_working_set_bytes", sample\n',
                '    return "traced_peak_bytes", sample\n',
            )
        ],
        "node": SUCCESS,
        "expect_regex": r'assert metric == "process_peak_working_set_bytes"',
    },
    "omit-cb": {
        "target": TEST,
        "edits": [
            ("        counters.cb = structure_size\n", "        counters.cb = 0\n")
        ],
        "node": SUCCESS,
        "expect_regex": r"assert samples ==",
    },
    "wrong-api-size": {
        "target": TEST,
        "edits": [
            (
                "        if not get_process_memory_info(process, ctypes.byref(counters), structure_size):\n",
                "        if not get_process_memory_info(process, ctypes.byref(counters), structure_size - 1):\n",
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"assert samples ==",
    },
    "packed-layout": {
        "target": TEST,
        "edits": [
            (
                "class PROCESS_MEMORY_COUNTERS(ctypes.Structure):\n    _fields_ = [\n",
                "class PROCESS_MEMORY_COUNTERS(ctypes.Structure):\n    _pack_ = 1\n    _fields_ = [\n",
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"PROCESS_MEMORY_COUNTERS\._fields_",
    },
    "field-type": {
        "target": TEST,
        "edits": [
            (
                'class PROCESS_MEMORY_COUNTERS(ctypes.Structure):\n    _fields_ = [\n        ("cb", ctypes.c_uint32),\n        ("PageFaultCount", ctypes.c_uint32),\n        ("PeakWorkingSetSize", ctypes.c_size_t),\n',
                'class PROCESS_MEMORY_COUNTERS(ctypes.Structure):\n    _fields_ = [\n        ("cb", ctypes.c_uint32),\n        ("PageFaultCount", ctypes.c_uint32),\n        ("PeakWorkingSetSize", ctypes.c_uint32),\n',
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"PROCESS_MEMORY_COUNTERS\._fields_",
    },
    "field-order": {
        "target": TEST,
        "edits": [
            (
                'class PROCESS_MEMORY_COUNTERS(ctypes.Structure):\n    _fields_ = [\n        ("cb", ctypes.c_uint32),\n        ("PageFaultCount", ctypes.c_uint32),\n        ("PeakWorkingSetSize", ctypes.c_size_t),\n        ("WorkingSetSize", ctypes.c_size_t),\n',
                'class PROCESS_MEMORY_COUNTERS(ctypes.Structure):\n    _fields_ = [\n        ("cb", ctypes.c_uint32),\n        ("PageFaultCount", ctypes.c_uint32),\n        ("WorkingSetSize", ctypes.c_size_t),\n        ("PeakWorkingSetSize", ctypes.c_size_t),\n',
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"PROCESS_MEMORY_COUNTERS\._fields_",
    },
    "reuse-structure": {
        "target": TEST,
        "edits": [
            (
                "    def sample():\n        counters = PROCESS_MEMORY_COUNTERS()\n",
                "    counters = PROCESS_MEMORY_COUNTERS()\n\n    def sample():\n",
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"structures\[0\] is not structures\[1\]",
    },
    "omit-signature": {
        "target": TEST,
        "edits": [
            (
                "    get_process_memory_info.restype = ctypes.c_int\n",
                "    get_process_memory_info.restype = None\n",
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"get_process_memory_info\.restype is ctypes\.c_int",
    },
    "replace-pseudo-handle": {
        "target": TEST,
        "edits": [
            (
                "        if not get_process_memory_info(process, ctypes.byref(counters), structure_size):\n",
                "        if not get_process_memory_info(ctypes.c_void_p(process), ctypes.byref(counters), structure_size):\n",
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"assert samples ==",
    },
    "close-pseudo-handle": {
        "target": TEST,
        "edits": [
            (
                "        process = get_current_process()\n        if not get_process_memory_info(process, ctypes.byref(counters), structure_size):\n",
                "        process = get_current_process()\n        close_handle = kernel32.CloseHandle\n        close_handle(process)\n        if not get_process_memory_info(process, ctypes.byref(counters), structure_size):\n",
            )
        ],
        "node": SUCCESS,
        "expect_regex": r"assert close_handle\.calls == \[\]",
    },
    "ignore-active-trace": {
        "target": TEST,
        "edits": [
            (
                "    if tracemalloc_module.is_tracing():\n",
                "    if False and tracemalloc_module.is_tracing():\n",
            )
        ],
        "node": FAILURE,
        "expect_regex": r"DID NOT RAISE",
    },
    "collapse-missing-exports": {
        "target": TEST,
        "edits": [
            (
                "    get_process_memory_info = kernel32.K32GetProcessMemoryInfo\n",
                "    get_process_memory_info = kernel32.GetCurrentProcess\n",
            )
        ],
        "node": FAILURE,
        "expect_regex": r"assert caught_error is missing_error",
    },
    "ignore-zero-return": {
        "target": TEST,
        "edits": [
            (
                "        if not get_process_memory_info(process, ctypes.byref(counters), structure_size):\n",
                "        if False and not get_process_memory_info(process, ctypes.byref(counters), structure_size):\n",
            )
        ],
        "node": FAILURE,
        "expect_regex": r"DID NOT RAISE",
    },
    "implicit-winerror": {
        "target": TEST,
        "edits": [
            (
                "            raise win_error(saved_error)\n",
                "            raise win_error()\n",
            )
        ],
        "node": FAILURE,
        "expect_regex": r"assert win_error\.calls == \[\(saved_error,\)\]",
    },
    "omit-crossing-finally": {
        "target": TEST,
        "edits": [
            (
                "    try:\n        result = operation()\n    finally:\n        protocol.decode_wire_json = original_decode\n        protocol.parse_snapshot = original_parse\n",
                "    result = operation()\n    protocol.decode_wire_json = original_decode\n    protocol.parse_snapshot = original_parse\n",
            )
        ],
        "node": FAILURE,
        "expect_regex": r"protocol\.decode_wire_json is original_decode",
    },
    "equivalent-crossing-restoration": {
        "target": TEST,
        "edits": [
            (
                "        protocol.decode_wire_json = original_decode\n",
                "        protocol.decode_wire_json = lambda *args, **kwargs: original_decode(*args, **kwargs)\n",
            )
        ],
        "node": FAILURE,
        "expect_regex": r"protocol\.decode_wire_json is original_decode",
    },
    "replace-sentinel": {
        "target": TEST,
        "edits": [
            (
                "        result = operation()\n",
                '        try:\n            result = operation()\n        except RuntimeError:\n            raise RuntimeError("replacement")\n',
            )
        ],
        "node": FAILURE,
        "expect_regex": r"caught\.value is sentinel",
    },
    "failure-success-counts": {
        "target": TEST,
        "edits": [
            (
                "    try:\n        result = operation()\n    finally:\n",
                '    try:\n        try:\n            result = operation()\n        except BaseException:\n            return None, calls["decode"], calls["parse"]\n    finally:\n',
            )
        ],
        "node": FAILURE,
        "expect_regex": r"DID NOT RAISE",
    },
    "raw-size": {
        "target": TEST,
        "edits": [('    buffer.write(b"]}")\n', '    buffer.write(b"]} ")\n')],
        "node": RESOURCE,
        "expect_regex": r"maximum raw payload size changed",
    },
    "row-count": {
        "target": TEST,
        "edits": [
            (
                '    for index in range(LIMITS["get_rows"]):\n',
                '    for index in range(LIMITS["get_rows"] - 1):\n',
            ),
            (
                '    raw = buffer.getvalue()\n    assert len(raw) == 47_022_137, "maximum raw payload size changed"\n',
                '    raw = buffer.getvalue()\n    raw += b" " * (47_022_137 - len(raw))\n    assert len(raw) == 47_022_137, "maximum raw payload size changed"\n',
            ),
        ],
        "node": RESOURCE,
        "expect_regex": r"maximum row cardinality changed",
    },
    "observation-data": {
        "target": TEST,
        "edits": [
            (
                '            else [{"name": name, "age_ms": LIMITS["activity_ms"] - 1} for name in names]\n',
                '            else [{"name": name, "age_ms": LIMITS["activity_ms"] - 1} for name in names[:-1]]\n',
            ),
            (
                '    raw = buffer.getvalue()\n    assert len(raw) == 47_022_137, "maximum raw payload size changed"\n',
                '    raw = buffer.getvalue()\n    raw += b" " * (47_022_137 - len(raw))\n    assert len(raw) == 47_022_137, "maximum raw payload size changed"\n',
            ),
        ],
        "node": RESOURCE,
        "expect_regex": r"maximum observation cardinality changed",
    },
    "read-amount": {
        "target": "wingman/fleetsharing/client.py",
        "edits": [
            (
                "                    (bound if status == 200 else MAX_RESPONSE_BYTES) + 1\n",
                "                    (bound if status == 200 else MAX_RESPONSE_BYTES) + 2\n",
            )
        ],
        "node": RESOURCE,
        "expect_regex": r"maximum response read amount changed",
    },
    "response-closure": {
        "target": TEST,
        "edits": [
            (
                "        def read(self, amount=-1):\n",
                "        def __exit__(self, *_args):\n            return False\n\n        def read(self, amount=-1):\n",
            )
        ],
        "node": RESOURCE,
        "expect_regex": r"maximum response was not closed",
    },
    "decoder-bypass": {
        "target": "wingman/fleetsharing/client.py",
        "edits": [
            (
                "    parsed = _parse(protocol.decode_wire_json, raw)\n",
                "    parsed = json.loads(raw)\n",
            )
        ],
        "node": RESOURCE,
        "expect_regex": r"wire decoder crossing count changed",
    },
    "decoder-duplicate": {
        "target": "wingman/fleetsharing/client.py",
        "edits": [
            (
                "    parsed = _parse(protocol.decode_wire_json, raw)\n",
                "    protocol.decode_wire_json(raw)\n    parsed = _parse(protocol.decode_wire_json, raw)\n",
            )
        ],
        "node": RESOURCE,
        "expect_regex": r"wire decoder crossing count changed",
    },
    "parser-bypass": {
        "target": "wingman/fleetsharing/client.py",
        "edits": [
            (
                '        return _parse(\n            protocol.parse_snapshot,\n            self._send_signed(\n                SNAPSHOT_PATH,\n                "GET",\n                b"",\n                session_id,\n                private_key,\n                revision,\n                now,\n                before_send=before_send,\n            ),\n        )\n',
                '        value = self._send_signed(\n            SNAPSHOT_PATH,\n            "GET",\n            b"",\n            session_id,\n            private_key,\n            revision,\n            now,\n            before_send=before_send,\n        )\n        return protocol.CombatSnapshot(\n            server_time_ms=value["server_time_ms"],\n            rows=tuple(protocol._combat_read_row(row) for row in value["rows"]),\n        )\n',
            )
        ],
        "node": RESOURCE,
        "expect_regex": r"snapshot parser crossing count changed",
    },
    "parser-duplicate": {
        "target": "wingman/fleetsharing/client.py",
        "edits": [
            (
                '        return _parse(\n            protocol.parse_snapshot,\n            self._send_signed(\n                SNAPSHOT_PATH,\n                "GET",\n                b"",\n                session_id,\n                private_key,\n                revision,\n                now,\n                before_send=before_send,\n            ),\n        )\n',
                '        value = self._send_signed(\n            SNAPSHOT_PATH,\n            "GET",\n            b"",\n            session_id,\n            private_key,\n            revision,\n            now,\n            before_send=before_send,\n        )\n        protocol.parse_snapshot(value)\n        return _parse(protocol.parse_snapshot, value)\n',
            )
        ],
        "node": RESOURCE,
        "expect_regex": r"snapshot parser crossing count changed",
    },
    "budget-zero": {
        "target": TEST,
        "edits": [
            (
                "MAXIMUM_RESPONSE_RESOURCE_BUDGET_S = 75.0\n",
                "MAXIMUM_RESPONSE_RESOURCE_BUDGET_S = 0.0\n",
            )
        ],
        "node": RESOURCE,
        "expect_regex": r"maximum response resource budget exceeded",
    },
    "child-wrong-metric": {
        "target": TEST,
        "edits": [
            (
                '        "memory_metric": metric,\n',
                '        "memory_metric": "traced_peak_bytes",\n',
            ),
            ('        "platform": sys.platform,\n', '        "platform": "win32",\n'),
        ],
        "node": RESOURCE,
        "expect_regex": r"process_peak_working_set_bytes",
        "junit_zero_resource": True,
    },
}


def git_bytes(*args):
    return subprocess.check_output(["git", "-C", str(W), *args])


def run_recipe(name):
    row = MUTATIONS[name]
    required_size = row.get("requires_pointer_size")
    if required_size is not None and ctypes.sizeof(ctypes.c_size_t) != required_size:
        return None, {"mutant": name, "result": "not-applicable-native-width"}
    target = W / row["target"]
    original = target.read_bytes()
    original_hash = hashlib.sha256(original).hexdigest()
    before_diff = git_bytes("diff", "--binary", "HEAD", "--", ".")
    before_status = git_bytes("status", "--porcelain=v2", "--untracked-files=all", "-z")
    mutated = original
    output = b""
    junit = Path(f"/tmp/windows-memory-mutant-{name}.xml")
    problem = None
    restoration_problem = None
    try:
        for before_text, after_text in row["edits"]:
            before = before_text.encode()
            after = after_text.encode()
            if mutated.count(before) != 1:
                raise AssertionError(
                    (name, "match-count", mutated.count(before), before_text)
                )
            if mutated.count(after) != 0:
                raise AssertionError((name, "replacement-already-present", after_text))
            mutated = mutated.replace(before, after, 1)
        target.write_bytes(mutated)
        result = subprocess.run(
            [
                str(P),
                "-m",
                "pytest",
                row["node"],
                "-q",
                "-p",
                "no:cacheprovider",
                f"--junitxml={junit}",
            ],
            cwd=W,
            env={**os.environ, "PYTHONPATH": str(W)},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=360,
        )
        output = result.stdout
        text = output.decode("utf-8", "replace")
        if result.returncode == 0:
            problem = AssertionError(f"{name}: mutant unexpectedly passed")
        elif re.search(row["expect_regex"], text) is None:
            problem = AssertionError(
                f"{name}: intended regex {row['expect_regex']!r} absent; output follows\n{text}"
            )
        if row.get("junit_zero_resource"):
            root = ET.parse(junit).getroot()
            properties = [
                prop.get("name", "")
                for prop in root.iter("property")
                if prop.get("name", "").startswith("resource.")
            ]
            if properties:
                problem = AssertionError(
                    f"{name}: rejected child evidence published {properties}"
                )
    except Exception as error:  # noqa: BLE001 -- report any recipe failure after restoration.
        problem = error
    finally:
        try:
            target.write_bytes(original)
            restored = target.read_bytes()
            if restored != original:
                raise AssertionError(f"{name}: restored bytes differ")
            if hashlib.sha256(restored).hexdigest() != original_hash:
                raise AssertionError(f"{name}: restored hash differs")
            if git_bytes("diff", "--binary", "HEAD", "--", ".") != before_diff:
                raise AssertionError(f"{name}: restored binary diff differs")
            if (
                git_bytes("status", "--porcelain=v2", "--untracked-files=all", "-z")
                != before_status
            ):
                raise AssertionError(f"{name}: restored status differs")
        except Exception as error:  # noqa: BLE001 -- restoration failures are fatal evidence.
            restoration_problem = error
        out = Path("/tmp/wingman-windows-memory-mutants")
        out.mkdir(exist_ok=True)
        (out / f"{name}.log").write_bytes(output)
        (out / f"{name}.json").write_text(
            json.dumps(
                {
                    "target": row["target"],
                    "original_sha256": original_hash,
                    "expect_regex": row["expect_regex"],
                    "problem": None if problem is None else repr(problem),
                    "restoration_problem": None
                    if restoration_problem is None
                    else repr(restoration_problem),
                },
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
    if restoration_problem is not None:
        raise restoration_problem
    return problem, {
        "mutant": name,
        "result": "intended-red" if problem is None else "failed",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("mutants", nargs="+", choices=tuple(MUTATIONS))
    args = parser.parse_args(argv)
    failures = []
    for name in args.mutants:
        try:
            problem, report = run_recipe(name)
        except Exception as error:  # noqa: BLE001 -- aggregate recipe and restoration failures.
            failures.append((name, error))
            print(
                json.dumps(
                    {
                        "mutant": name,
                        "result": "restoration-failed",
                        "error": repr(error),
                    }
                )
            )
            break
        print(json.dumps(report, sort_keys=True))
        if problem is not None:
            failures.append((name, problem))
    if failures:
        for name, error in failures:
            print(f"{name}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
python -m py_compile /tmp/windows_memory_mutation.py
```

The `raw-size` replacement is formatter-sensitive; before running the catalog, require `python -m py_compile tests/test_fleetsharing_transport_resources.py` and verify every catalog `before` string matches exactly once. If the committed source differs from the exact snippets in this plan, stop and review rather than weakening match-once restoration.

---

### Task 1: Freeze cc48c887 / PR #288 Executable Baseline

**Files:**
- Create: `docs/ci-windows-resource-memory-probe-results.md`
- Read: `tests/test_fleetsharing_transport_resources.py`
- Read: `.github/workflows/ci.yml`
- Read: `scripts/summarize_pytest_junit.py`
- Read: `tests/test_ci_timing.py`
- Read: `docs/ci-test-budget-redesign.md`
- Read: `docs/ci-test-budget-fleet-tranche-results.md`
- Read: `docs/superpowers/plans/2026-09-24-setup-controller-fixture-construction.md`
- Read: `docs/ci-setup-controller-fixture-construction-results.md`
- Read: `/tmp/wingman-setup-hosted-36051546735/{selected.json,hosted-audit.json,logs/*,artifacts/{ubuntu,windows}/*}`

**Interfaces:**
- Consumes: merged baseline `cc48c887`, PR #288 artifact roots, exact three target IDs, complete 16,607-ID inventory, existing six-property resource schema.
- Produces: `/tmp/wingman-windows-memory-baseline/*` and the committed baseline sections of `docs/ci-windows-resource-memory-probe-results.md`; Tasks 2–5 use these inventories and hashes as authority.

- [ ] **Step 1: Confirm checkout and authority before writing**

Run:

```bash
git status --short --branch
git log -5 --oneline
git show -s --format='%H%n%s%n%P' cc48c887
```

Expected after this review correction is committed: branch `ci-windows-resource-memory-probe`; the four approved design/plan commits that existed at review time plus `docs: make Windows memory plan executable` above `cc48c887`; no uncommitted files; baseline subject `Optimize setup controller fixture construction (#288)` with parent `c23788e392bcd586dfc95b7390eaee18cb4ec224`.

- [ ] **Step 2: Run Reproducibility Block A**

Run the complete Block A exactly, including both compile commands.

Expected: the exact counts, identities, properties, timings, provenance, job IDs, artifact IDs/digests, and skip counts stated under Block A. Treat any mismatch as stale/missing artifact evidence and stop.

- [ ] **Step 3: Create the results ledger with exact baseline evidence**

Create `docs/ci-windows-resource-memory-probe-results.md` with these sections in this order:

```markdown
# Windows resource memory probe results

## Scope and authority
## Task status
## Exact three-ID target baseline
## Exact 16,607-ID complete baseline
## PR #288 executable provenance
## PR #288 jobs and artifacts
## Baseline resource evidence and timing
## Complete normalized Ubuntu skip tuples
## Complete normalized Windows skip tuples
## Baseline review
## Concerns
```

Populate it from `/tmp/wingman-windows-memory-baseline/summary.json`, `target-3.txt`, `complete-16607.txt`, `ubuntu-skips.json`, and `windows-skips.json`. Record all of these exact facts:

- source `cc48c887ac3a140a2baf87d4bdcc3f6e916c02c9`;
- the three exact target IDs in artifact/source order;
- suite count `16,607`, target count `3`, ordinary count `2`, resource count `1`;
- run `36051546735`, attempt `1`, synthetic `515c6185789fc0c67c8cd6247f57569bc8a45076`, head `9d60c726dbe0d74263e59d865723e9575831f7a9`, base `c23788e392bcd586dfc95b7390eaee18cb4ec224`, and `run_pull_request_metadata: absent`;
- jobs checks `107808061930`, Ubuntu `107808061903`, Windows `107808061529`;
- artifacts Ubuntu `10830398935` digest `sha256:2fe063a4448799e112f0518c938b9bc817f3078c67035daed7423293524116c0`, Windows `10831516363` digest `sha256:4516bded043e3436cb4aa41eda622324e448a3c9d90656062487cb0cf759e1f3`;
- Ubuntu Python `3.11.16`, `process_peak_rss_kib`, peak `455040`, child wall `4.133140558999997`, testcase `4.134`, target-file sum `4.163`;
- Windows Python `3.11.9` x64, `traced_peak_bytes`, peak `282144272`, child wall `45.94401130000006`, testcase `45.946`, target-file sum `46.001`;
- exact six resource properties, exact bytes/rows/observations, Ubuntu `16593 passed + 14 skipped`, Windows `16540 passed + 67 skipped`;
- job observations: checks `13s`, Ubuntu Test `295s` / job `327s`, Windows Test `757s` / job `877s`;
- baseline is observational and supports no speedup claim.

Include the complete normalized skip tuples, not only counts. Preserve artifact order.

- [ ] **Step 4: Independently review Task 1 evidence**

Use a fresh reviewer to compare the ledger with the approved spec, Block A output, both timing JSON files, both JUnit files, `selected.json`, and the three logs. Require explicit review of identity order, one-marker ownership, resource property strings, Python/platform provenance, artifact/job selection, and complete skips. Record findings and any corrections under `## Baseline review`.

- [ ] **Step 5: Verify documentation-only scope and commit Task 1**

Run:

```bash
git diff --check
git status --short
git diff --name-only
```

Expected changed path: `docs/ci-windows-resource-memory-probe-results.md` only.

Commit:

```bash
git add docs/ci-windows-resource-memory-probe-results.md
git commit -m "docs: freeze Windows memory probe baseline"
```

---

### Task 2: TDD Native Peak-Working-Set Success and ABI Contract

**Files:**
- Modify: `tests/test_fleetsharing_transport_resources.py`
- Modify: `docs/ci-windows-resource-memory-probe-results.md`
- Test: `tests/test_fleetsharing_transport_resources.py::test_windows_memory_probe_reports_peak_working_set_without_tracing`

**Interfaces:**
- Consumes: Task 1 exact three-ID prefix and complete 16,607 inventory.
- Produces: lazy `_windows_memory_probe()`, injectable `memory_probe()`, natural `PROCESS_MEMORY_COUNTERS`, portable fakes, exact first suffix identity, target `4`, complete `16,608`.

- [ ] **Step 1: Append the exact first test and portable fakes before implementation**

Add `ctypes` and `os` imports, the five fake classes, exactly `test_windows_memory_probe_reports_peak_working_set_without_tracing`, and the explicit non-Windows fallback adaptation from the Intended Final Test-Module Interfaces. The first identity must accept `monkeypatch`, install `_TraceSeam` as the actual `sys.modules["tracemalloc"]`, and retain that module through native setup, guard, repeated samples, and final assertions. Do not add the second identity, crossing helper, or resource integration yet.

- [ ] **Step 2: Run the first identity and verify RED**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py::test_windows_memory_probe_reports_peak_working_set_without_tracing \
  -q
```

Expected: `1 failed`; earliest owned failure is missing `PROCESS_MEMORY_COUNTERS`, the new `memory_probe` seams, or `_require_untraced_windows_decode`. The adapted fallback identity remains collected under its original ID. The RED must not resolve or import a real Windows DLL on Linux.

- [ ] **Step 3: Implement the structure, lazy native success path, and platform selection**

Add `_MISSING`, `PROCESS_MEMORY_COUNTERS`, `_windows_memory_probe`, and the new `memory_probe` exactly as shown. For this task's initial zero-return branch, this loud interim is acceptable:

```python
        if not get_process_memory_info(process, ctypes.byref(counters), structure_size):
            raise RuntimeError("K32GetProcessMemoryInfo failed.")
```

Add `_require_untraced_windows_decode` exactly as shown so the first identity imports the actual fake `sys.modules["tracemalloc"]`, records one `is_tracing()` call, and proves native setup/sampling/cleanup call neither tracing start nor stop. Do not integrate the guard into `measure_response()` until Task 3.

- [ ] **Step 4: Run focused GREEN and portable fallback coverage**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py::test_windows_memory_probe_reports_peak_working_set_without_tracing \
  tests/test_fleetsharing_transport_resources.py::test_memory_probe_falls_back_without_resource \
  -q
```

Expected: `2 passed`; the success test executes on Linux entirely through fake native exports plus the actual fake `tracemalloc` module, and the existing explicitly non-Windows fallback still reports `traced_peak_bytes` and stops its own tracer in `finally`.

- [ ] **Step 5: Prove exact interim inventory `3 -> 4` and suite `16,607 -> 16,608`**

Materialize and compile Reproducibility Block B1, then run:

```bash
uv run --no-sync python /tmp/windows_memory_interim.py
```

Expected: exact target order is the baseline three followed by the first suffix ID; the complete ordered inventory equals the 16,607 baseline with that ID inserted immediately after the baseline target anchor; exact additions/removals are `+1/0`; count/hash is `16,608`; all baseline IDs retain relative order; marker ownership remains exactly one; and the exact Task 2 path set is enforced.

Run the ordinary target selection:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py \
  -m "not resource" -q
```

Expected: `3 passed, 1 deselected`.

- [ ] **Step 6: Qualify success/ABI mutations and restore each one**

Materialize and compile Block C now, then invoke its Task 2 subset in one aggregate command:

```bash
uv run --no-sync python /tmp/windows_memory_mutation.py \
  windows-to-resource windows-to-tracing start-tracing stop-tracing \
  current-working-set width-truncation signed-coercion wrong-native-metric \
  omit-cb wrong-api-size packed-layout field-type field-order reuse-structure \
  omit-signature replace-pseudo-handle close-pseudo-handle
```

Expected: one `intended-red` record per applicable recipe and aggregate exit `0`. `windows-to-resource` reaches the exact metric assertion through the usable resource seam. `windows-to-tracing` and `start-tracing` perform a real `import tracemalloc`, activate the installed fake module, and fail at the active-tracer guard; `stop-tracing` fails the exact no-stop assertion. Remaining recipes fail their owned value, width, signedness, field type/order, `cb`, byte-size, layout/alignment/no-pack, fresh-structure, signature, pseudo-handle identity, or no-`CloseHandle` assertion. `width-truncation` is explicitly reported not-applicable only on a 32-bit interpreter; the signed-coercion recipe still qualifies that width. Every recipe restores exact bytes/hash/binary diff/status before the aggregate runner continues.

- [ ] **Step 7: Record Task 2 evidence and run an independent review**

Append TDD RED/GREEN output, interim inventory/hashes, mutation table, and exact restoration hashes to the results ledger. A fresh reviewer must inspect structure fields/order/offset formula/size/alignment, no `_pack_`, lazy `WinDLL`, signatures, pseudo-handle/no-close behavior, fresh samples, `PeakWorkingSetSize` selection, width-conditional values, Windows-before-resource selection, and no trace start/stop. Resolve every finding before commit.

- [ ] **Step 8: Verify scope and commit Task 2**

Run:

```bash
python -m py_compile tests/test_fleetsharing_transport_resources.py
uv run --extra dev ruff check tests/test_fleetsharing_transport_resources.py
uv run --extra dev ruff format --check tests/test_fleetsharing_transport_resources.py
git diff --check
git diff --name-only
```

Expected changed paths: target test and results ledger only.

Commit:

```bash
git add tests/test_fleetsharing_transport_resources.py \
  docs/ci-windows-resource-memory-probe-results.md
git commit -m "test: add Windows peak working set probe"
```

---

### Task 3: Fail Closed, Restore Crossings, and Gate Parent Evidence

**Files:**
- Modify: `tests/test_fleetsharing_transport_resources.py`
- Modify: `docs/ci-test-budget-redesign.md`
- Modify: `docs/ci-windows-resource-memory-probe-results.md`
- Test: `tests/test_fleetsharing_transport_resources.py::test_windows_memory_probe_fails_closed_and_restores_crossings`
- Test: `tests/test_fleetsharing_transport_resources.py::test_maximum_legal_response_actual_reader_and_codec_in_subprocess`

**Interfaces:**
- Consumes: Task 2 native success probe and first suffix identity.
- Produces: saved-error fail-closed behavior, exact named-export failures, active-trace guard, `_measure_protocol_crossings`, exact-one decoder/parser assertions, immediate parent metric gate, exact second suffix identity, final target `5`, complete `16,609`.

- [ ] **Step 1: Append the exact second test before implementation**

Append exactly `test_windows_memory_probe_fails_closed_and_restores_crossings` from the final interface block after the first suffix identity. Do not parameterize it.

- [ ] **Step 2: Run the second identity and verify RED**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py::test_windows_memory_probe_fails_closed_and_restores_crossings \
  -q
```

Expected: `1 failed`; earliest owned failure is the interim zero-return `RuntimeError`, missing `_measure_protocol_crossings`, or absent exact saved-error behavior. The failure must not construct the 47 MB response.

- [ ] **Step 3: Implement exact native failure behavior**

Replace the Task 2 interim zero-return branch with:

```python
        if not get_process_memory_info(process, ctypes.byref(counters), structure_size):
            saved_error = get_last_error()
            raise win_error(saved_error)
```

Do no unrelated work between the zero return and `get_last_error()`. Keep loader and both named export lookups unsuppressed. Do not add fallback recovery.

- [ ] **Step 4: Add and integrate the trace guard and crossing helper**

Add `_measure_protocol_crossings` exactly as specified. In `measure_response()`:

1. call `_require_untraced_windows_decode()` as the first executable line, before payload construction, native setup, sampling, or decode;
2. construct and close the complete payload only after the guard passes;
3. keep `memory_before_client` and `memory_peak` as absolute samples;
4. invoke the actual signed client through `_measure_protocol_crossings`;
5. require exact-one decoder and parser calls only after successful return;
6. retain exact result/cardinality/read/closure assertions.

Use the exact code and assertion messages from the interface section.

- [ ] **Step 5: Add the immediate parent Windows metric gate**

Use the exact parent ordering block. Verify by direct source inspection that `json.loads(result.stdout)` is followed immediately by the conditional Windows metric assertion, then only after that by parent-derived wall evidence, property publication, and budget evaluation.

- [ ] **Step 6: Prove actual externally traced child refusal without another identity**

Keep the child invocation inside the second ordinary identity exactly as shown. It sets `PYTHONTRACEMALLOC=1`, carries `--measure` in `sys.argv`, and on non-Windows hosts uses a `runpy` bootstrap only to select `sys.platform == "win32"` after portable imports. Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py::test_windows_memory_probe_fails_closed_and_restores_crossings \
  -q
```

Expected: `1 passed`; the nested child exits nonzero at the pre-payload/pre-decode guard, stdout is exactly empty, stderr contains `requires tracemalloc to be disabled`, and the installed active fake remains active with zero `start()`/`stop()` calls. On hosted Windows the same identity uses the real direct `--measure` child path.

- [ ] **Step 7: Run both new ordinary tests and verify GREEN**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py::test_windows_memory_probe_reports_peak_working_set_without_tracing \
  tests/test_fleetsharing_transport_resources.py::test_windows_memory_probe_fails_closed_and_restores_crossings \
  -q
```

Expected: `2 passed`. The failure identity must cover, inside one ID: loader sentinel, distinct missing-`GetCurrentProcess`, distinct missing-`K32GetProcessMemoryInfo`, explicit last-error/WinError seams in every native scenario, zero return with exact saved code, `_WinErrorSeam.calls == [(saved_error,)]`, no fallback, no trace start/stop, active external tracer left active, the real traced child refusal, tiny decoder/parser touch, exact original restoration, and original sentinel identity.

- [ ] **Step 8: Run the full maximum subprocess with JUnit evidence**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py \
  -m resource -q -s --durations=0 \
  --junitxml=/tmp/windows-memory-resource.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/windows-memory-resource.xml /tmp/windows-memory-resource.json
```

Directly assert the XML properties rather than relying only on summarized output:

```bash
python - <<'PY'
import xml.etree.ElementTree as ET

root = ET.parse("/tmp/windows-memory-resource.xml").getroot()
cases = list(root.iter("testcase"))
assert len(cases) == 1
properties = {
    prop.get("name"): prop.get("value")
    for prop in cases[0].findall("./properties/property")
    if prop.get("name", "").startswith("resource.")
}
assert set(properties) == {
    "resource.subprocess_wall_seconds",
    "resource.memory_metric",
    "resource.memory_peak",
    "resource.raw_bytes",
    "resource.rows",
    "resource.observations",
}
assert properties["resource.memory_metric"] == "process_peak_rss_kib"
assert properties["resource.raw_bytes"] == "47022137"
assert properties["resource.rows"] == "8192"
assert properties["resource.observations"] == "155648"
assert int(properties["resource.memory_peak"]) > 0
assert float(properties["resource.subprocess_wall_seconds"]) <= 75
PY
```

Expected on Linux: `1 passed, 4 deselected`; the direct assertions pass; one generic summarizer resource-evidence row is preserved without a summarizer edit.

- [ ] **Step 9: Update only the current Transport resources paragraph**

In `docs/ci-test-budget-redesign.md`, replace this exact current paragraph:

```markdown
The 47 MB gate owns successful decoding of the maximum supported response through
the real reader and codec, including exact byte and row counts. It does not own a
stable peak-allocation ceiling: Windows `tracemalloc` peak is retained as
observability, not a pass/fail metric. Its initial Windows case budget is 75
seconds, reviewed after the comparable-run sample; the complete product gate's
600-second ceiling remains authoritative. A wall-time over the case budget fails
with the recorded elapsed and peak values.
```

with this exact paragraph:

```markdown
The 47 MB gate owns successful decoding of the maximum supported response through
the real reader and codec, including exact byte and row counts. On Windows it
reports `K32GetProcessMemoryInfo`'s native process-lifetime peak working set as
`process_peak_working_set_bytes`; Linux and macOS retain their existing
`ru_maxrss` metric semantics. An externally active Windows tracer fails the test
before payload construction or decode and is never stopped. These values are
observability, not a pass/fail memory ceiling, decode-only allocation peak, or
before/after delta. The initial Windows case budget remains 75 seconds; the
complete product gate's 600-second ceiling remains authoritative. A wall-time
over the case budget fails with the recorded elapsed and peak values.
```

Do not edit the historical 44.6-second reference row or any other section.

- [ ] **Step 10: Prove exact final inventory and scope**

Run:

```bash
uv run --no-sync python /tmp/windows_memory_endpoint.py
```

Expected: target `5`, ordinary `4`, resource `1`, suite `16609`, exact suffix order, zero removals, and only allowed paths.

- [ ] **Step 11: Run the complete mutation catalog**

Recompile Block C and run the complete catalog in one aggregate invocation:

```bash
uv run --no-sync python /tmp/windows_memory_mutation.py \
  windows-to-resource windows-to-tracing start-tracing stop-tracing \
  current-working-set width-truncation signed-coercion wrong-native-metric \
  omit-cb wrong-api-size packed-layout field-type field-order reuse-structure \
  omit-signature replace-pseudo-handle close-pseudo-handle ignore-active-trace \
  collapse-missing-exports ignore-zero-return implicit-winerror \
  omit-crossing-finally equivalent-crossing-restoration replace-sentinel \
  failure-success-counts raw-size row-count observation-data read-amount \
  response-closure decoder-bypass decoder-duplicate parser-bypass \
  parser-duplicate budget-zero child-wrong-metric
```

Expected: every applicable row reports `intended-red`, the aggregate command exits `0`, and every target restores exact pre-probe bytes/hash/binary diff/status. `collapse-missing-exports` uses explicit last-error and `_WinErrorSeam` arguments and fails `assert caught_error is missing_error`, so it cannot fail through absent Linux `ctypes` members. `implicit-winerror` still raises the original sentinel but fails the exact `win_error.calls == [(saved_error,)]` assertion. `equivalent-crossing-restoration` fails exact object identity, and `failure-success-counts` fails because a failed operation may not return successful counts. `observation-data` changes generated names, pads only trailing JSON whitespace to preserve raw bytes, and therefore reaches the independent observation-cardinality assertion. `child-wrong-metric` changes child-reported platform/metric while leaving the parent untouched; its JUnit contains zero `resource.*` properties. Do not add a `_validate_success_headers` mutant; unchanged focused client tests and scope audit own that boundary.

- [ ] **Step 12: Record Task 3 evidence and independently review**

Append RED/GREEN output, exact final inventory, resource properties, each mutant's intended assertion, restoration hashes, and the docs paragraph diff to the results ledger. A fresh reviewer must inspect failure separation, saved-error ordering, no fallback/trace, active tracer ownership, helper `finally`, exact-object restoration, sentinel identity, exact-one success counts, maximum contract, parent publication ordering, zero-property rejection, and the unsupported success-header boundary. Resolve findings before commit.

- [ ] **Step 13: Verify and commit Task 3**

Run:

```bash
python -m py_compile tests/test_fleetsharing_transport_resources.py
uv run --extra dev ruff check tests/test_fleetsharing_transport_resources.py
uv run --extra dev ruff format --check tests/test_fleetsharing_transport_resources.py
git diff --check
git diff --name-only
```

Expected changed paths since Task 2: target test, results ledger, and current budget-design doc.

Commit:

```bash
git add tests/test_fleetsharing_transport_resources.py \
  docs/ci-test-budget-redesign.md \
  docs/ci-windows-resource-memory-probe-results.md
git commit -m "test: fail closed Windows resource memory probe"
```

---

### Task 4: Prove the Complete Local Endpoint

**Files:**
- Modify: `docs/ci-windows-resource-memory-probe-results.md`
- Verify unchanged: `tests/test_ci_timing.py`
- Verify unchanged: `scripts/summarize_pytest_junit.py`
- Verify unchanged: `.github/workflows/ci.yml`
- Verify unchanged: all production/dependency/configuration paths

**Interfaces:**
- Consumes: final Task 3 implementation and endpoint audit.
- Produces: complete local evidence for target `5`, suite `16,609`, resource properties, full maximum execution, complete suite `16,595 passed + 14 skipped`, tools, scope, and mutation restoration.

- [ ] **Step 1: Rebuild mandatory local prerequisites**

Run:

```bash
uv sync --locked --extra dev
node --version
cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available(), 'Native integration tests require the built codec'"
```

Expected: all exit `0`; Node prints a version; Cargo release build succeeds; codec availability assertion emits no error.

- [ ] **Step 2: Re-run exact endpoint and target selections**

Run:

```bash
uv run --no-sync python /tmp/windows_memory_endpoint.py
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py \
  -m "not resource" -q -rs --junitxml=/tmp/windows-memory-ordinary.xml
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py \
  -q -rs --durations=0 --junitxml=/tmp/windows-memory-target.xml
```

Expected: endpoint `5/4/1/16609`; ordinary `4 passed, 1 deselected`; full target `5 passed`; exact original three-ID prefix plus exact two-ID suffix.

- [ ] **Step 3: Re-run the full maximum subprocess and inspect all six properties**

Run the full subprocess again with fixed fresh paths:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py \
  -m resource -q -s --durations=0 \
  --junitxml=/tmp/windows-memory-resource-final.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/windows-memory-resource-final.xml \
  /tmp/windows-memory-resource-final.json
```

Expected: `1 passed, 4 deselected`; Linux metric remains `process_peak_rss_kib`; exact six properties, cardinalities, positive peak, and 75-second budget are later re-read directly by Block B3 rather than inferred from console text.

- [ ] **Step 4: Run the complete Fleet transport area**

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_client.py \
  tests/test_fleetsharing_transport_resources.py \
  tests/test_fleetsharing_transport_v2.py \
  tests/test_fleetsharing_wire_json.py \
  -q -rs --durations=30 \
  --junitxml=/tmp/windows-memory-fleet-transport.xml
```

Expected: `535 passed`; no skips; unchanged client header validation remains green; maximum resource executes once.

- [ ] **Step 5: Run the complete suite with JUnit and summarize it**

Run:

```bash
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/windows-memory-full.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/windows-memory-full.xml /tmp/windows-memory-full.json
```

Expected: exactly `16595 passed, 14 skipped` for `16609` outcomes; no Node, codec, or unexpected native-availability skip; timing JSON `case_count=16609`; target file `5` cases; one resource-evidence row with six properties; Linux metric unchanged.

- [ ] **Step 6: Run the exact local evidence audit and record skips**

Materialize and compile Block B3, then run:

```bash
uv run --no-sync python /tmp/windows_memory_local_audit.py
```

Expected: complete ordered inventory equals Block B's `complete-16609.txt`; target order equals `target-5.txt`; both new IDs are `passed`; full outcome is exactly `16,595 passed + 14 skipped`; normalized skip tuples equal Task 1's Ubuntu baseline byte-for-data and in order; direct resource XML has exactly six properties and Linux RSS; timing JSON has `case_count=16609` and one matching resource row; complete/target hashes are returned; changed paths equal the exact five-path set. Record the complete normalized skip list and audit JSON in the results ledger.

- [ ] **Step 7: Run independent gates**

Run:

```bash
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --no-sync python -m pytest tests/test_documentation.py -q
```

Expected: JS `PASS every page module loaded`; Cargo `1 passed; 0 failed`; Ruff check passes; Ruff format check passes; documentation tests `7 passed`.

- [ ] **Step 8: Audit protected paths and exact five-path scope**

Run:

```bash
git diff --check cc48c887..HEAD
git diff --name-only cc48c887..HEAD
git diff --name-only cc48c887..HEAD -- wingman .github scripts tests/test_ci_timing.py pyproject.toml uv.lock packaging
git status --short
```

Expected complete tranche names are contained by the exact five-path allowlist; the protected-path command prints no output. Run an explicit Python set comparison rather than trusting visual inspection.

- [ ] **Step 9: Re-run all mutations from a clean pre-probe state**

Run the complete Block C loop again. Then run:

```bash
git diff --check
git status --short
git diff --binary HEAD -- wingman/fleetsharing/client.py
```

Expected: all mutants intended-red; no production diff; only the results ledger is uncommitted.

- [ ] **Step 10: Perform required local self-review**

Record explicit pass/fail rows in the results ledger for:

- unfinished-marker/debug-output scan;
- identity arithmetic `3 + 2 = 5` and `16,607 + 2 = 16,609`;
- exact ABI fields/order/offsets/size/alignment/signatures/handle/`cb`/fresh structures/no pack/no close;
- exact metric and Peak-vs-current/pagefile values on native width;
- all four native failure scenarios and exact causes;
- explicit non-Windows fallback;
- external tracing ownership and zero test-owned start/stop;
- maximum bytes/rows/observations/read/closure/client/decoder/parser/timeout/budget;
- immediate parent metric gate and zero-property rejection;
- success-header boundary owned elsewhere;
- crossing restoration/sentinel behavior;
- mutation restoration;
- Linux/macOS compatibility;
- exact five-path scope and protected paths;
- no runtime/memory-ceiling/delta/speedup claim.

- [ ] **Step 11: Independently review the full local endpoint**

Use a fresh reviewer to inspect the entire diff from `cc48c887`, the spec, all Task 4 outputs, `/tmp` JUnit/timing evidence, and mutation logs. Resolve all correctness or maintainability findings, rerun affected focused checks, then rerun endpoint collection and `git diff --check`.

- [ ] **Step 12: Commit local results**

Commit only the ledger update:

```bash
git add docs/ci-windows-resource-memory-probe-results.md
git commit -m "docs: record local Windows memory probe verification"
```

---

## Reproducibility Block D — authorized hosted collector and audit

Run this block only after Task 5's explicit publication authorization. `NEW_RUN` and `PR_NUMBER` are mandatory; no latest-run inference is permitted. The collector accepts an empty run `pull_requests` array, but still requires explicit PR/run inputs, logs-primary synthetic/head/base agreement across checks/Ubuntu/Windows, current PR head/base corroboration, exact merge parents, current-attempt successful jobs, exact-name/time-window artifacts, and a five-path synthetic diff.

```bash
cat > /tmp/windows_memory_hosted_collect.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
: "${NEW_RUN:?Set NEW_RUN to the authorized workflow run ID}"
: "${PR_NUMBER:?Set PR_NUMBER to the authorized pull request number}"
R="elboaf/FlyGD-Wingman"
W="/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-resource-memory-probe"
O="/tmp/wingman-windows-memory-hosted-${NEW_RUN}"
rm -rf "$O"
mkdir -p "$O/logs" "$O/artifacts"
cd "$W"

gh api "repos/$R/actions/runs/$NEW_RUN" > "$O/run.json"
ATTEMPT=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_attempt"])' "$O/run.json")
gh run view "$NEW_RUN" -R "$R" --attempt "$ATTEMPT" --json databaseId,headSha,status,conclusion,url,jobs > "$O/run-view.json"
gh pr view "$PR_NUMBER" -R "$R" --json number,url,headRefName,headRefOid,baseRefName,baseRefOid > "$O/pr.json"
for attempt in $(seq 1 "$ATTEMPT"); do
  gh api "repos/$R/actions/runs/$NEW_RUN/attempts/$attempt" > "$O/run-attempt-$attempt.json"
  gh api "repos/$R/actions/runs/$NEW_RUN/attempts/$attempt/jobs?per_page=100" > "$O/jobs-attempt-$attempt.json"
done
cp "$O/jobs-attempt-$ATTEMPT.json" "$O/jobs.json"
gh api --paginate "repos/$R/actions/runs/$NEW_RUN/artifacts?per_page=100" --slurp > "$O/artifact-pages.json"

python - "$O" "$PR_NUMBER" <<'PY'
from __future__ import annotations
import json, sys
from pathlib import Path

out = Path(sys.argv[1])
pr_number = int(sys.argv[2])
run = json.loads((out / "run.json").read_text())
view = json.loads((out / "run-view.json").read_text())
pr = json.loads((out / "pr.json").read_text())
jobs = json.loads((out / "jobs.json").read_text())["jobs"]
assert run["event"] == "pull_request"
assert run["conclusion"] == view["conclusion"] == "success"
assert run["head_sha"] == view["headSha"]
assert pr["number"] == pr_number
roles = {
    "checks": "checks",
    "ubuntu": "test (ubuntu-latest)",
    "windows": "test (windows-latest)",
}
selected = {}
for role, name in roles.items():
    rows = [job for job in jobs if job["name"] == name]
    assert len(rows) == 1, (role, rows)
    job = rows[0]
    assert job["run_attempt"] == run["run_attempt"]
    assert job["conclusion"] == "success"
    selected[role] = job
(out / "selection.json").write_text(
    json.dumps(
        {
            "run_id": run["id"],
            "run_attempt": run["run_attempt"],
            "run_head_sha": run["head_sha"],
            "explicit_pr_number": pr_number,
            "current_pr": pr,
            "jobs": selected,
        },
        sort_keys=True,
        indent=2,
    )
    + "\n"
)
for role, job in selected.items():
    (out / f"{role}-job-id").write_text(str(job["id"]))
PY

for role in checks ubuntu windows; do
  JOB_ID=$(cat "$O/$role-job-id")
  gh api --allow-escape-sequences "repos/$R/actions/jobs/$JOB_ID/logs" > "$O/logs/$role.log"
done

python - "$O" <<'PY'
from __future__ import annotations
import json, re, sys
from pathlib import Path

out = Path(sys.argv[1])
metadata = json.loads((out / "selection.json").read_text())
run = json.loads((out / "run.json").read_text())
pr = json.loads((out / "pr.json").read_text())
merge_pattern = re.compile(
    r"HEAD is now at (?P<short>[0-9a-f]{7,40}) Merge "
    r"(?P<head>[0-9a-f]{40}) into (?P<base>[0-9a-f]{40})"
)
full_pattern = re.compile(r"(?P<sha>[0-9a-f]{40})\s*$")


def checkout(path):
    lines = path.read_text(errors="replace").splitlines()
    merges = [m for line in lines if (m := merge_pattern.search(line))]
    commands = [
        i
        for i, line in enumerate(lines)
        if "[command]" in line and "log -1 --format=%H" in line
    ]
    assert len(merges) == len(commands) == 1, (path, merges, commands)
    full = full_pattern.search(lines[commands[0] + 1])
    assert full
    synthetic = full.group("sha")
    assert synthetic.startswith(merges[0].group("short"))
    return {
        "synthetic_merge": synthetic,
        "merge_head": merges[0].group("head"),
        "merge_base": merges[0].group("base"),
    }


rows = {
    role: checkout(out / f"logs/{role}.log") for role in ("checks", "ubuntu", "windows")
}
triples = {
    (row["synthetic_merge"], row["merge_head"], row["merge_base"])
    for row in rows.values()
}
assert len(triples) == 1
synthetic, head, base = triples.pop()
assert head == run["head_sha"] == metadata["run_head_sha"]
run_prs = run.get("pull_requests") or []
assert len(run_prs) <= 1
run_pr_metadata = "absent" if not run_prs else "present"
if run_prs:
    entry = run_prs[0]
    if entry.get("number") is not None:
        assert entry["number"] == metadata["explicit_pr_number"]
    if (entry.get("head") or {}).get("sha"):
        assert entry["head"]["sha"] == head
    if (entry.get("base") or {}).get("sha"):
        assert entry["base"]["sha"] == base
metadata.update(
    {
        "synthetic_merge": synthetic,
        "head": head,
        "base": base,
        "checkout": rows,
        "run_pull_request_metadata": run_pr_metadata,
        "run_pull_request_entry": run_prs[0] if run_prs else None,
    }
)
(out / "selected.json").write_text(
    json.dumps(metadata, sort_keys=True, indent=2) + "\n"
)
PY

SYNTHETIC=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["synthetic_merge"])' "$O/selected.json")
HEAD_SHA=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["head"])' "$O/selected.json")
BASE_SHA=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["base"])' "$O/selected.json")
git fetch --quiet --no-tags origin "$SYNTHETIC" "$HEAD_SHA" "$BASE_SHA"
read -r COMMIT PARENT_BASE PARENT_HEAD EXTRA <<< "$(git rev-list --parents -n 1 "$SYNTHETIC")"
test "$COMMIT" = "$SYNTHETIC"
test "$PARENT_BASE" = "$BASE_SHA"
test "$PARENT_HEAD" = "$HEAD_SHA"
test -z "${EXTRA:-}"
CURRENT_PR_HEAD=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["headRefOid"])' "$O/pr.json")
CURRENT_PR_BASE=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["baseRefOid"])' "$O/pr.json")
test "$CURRENT_PR_HEAD" = "$HEAD_SHA"
test "$CURRENT_PR_BASE" = "$BASE_SHA"
git fetch --quiet origin "+refs/pull/$PR_NUMBER/merge:refs/remotes/pull/$PR_NUMBER/merge"
test "$(git rev-parse refs/remotes/pull/$PR_NUMBER/merge)" = "$SYNTHETIC"

python - "$O" <<'PY'
from __future__ import annotations
import json, sys
from datetime import datetime
from pathlib import Path

out = Path(sys.argv[1])
metadata = json.loads((out / "selected.json").read_text())
pages = json.loads((out / "artifact-pages.json").read_text())
artifacts = [row for page in pages for row in page["artifacts"]]


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


selected = {}
for role, name in {
    "ubuntu": "pytest-evidence-ubuntu-latest",
    "windows": "pytest-evidence-windows-latest",
}.items():
    job = metadata["jobs"][role]
    rows = [
        artifact
        for artifact in artifacts
        if artifact["name"] == name
        and not artifact["expired"]
        and stamp(job["started_at"])
        <= stamp(artifact["created_at"])
        <= stamp(job["completed_at"])
    ]
    assert len(rows) == 1, (role, rows)
    selected[role] = rows[0]
metadata["artifacts"] = selected
(out / "selected.json").write_text(
    json.dumps(metadata, sort_keys=True, indent=2) + "\n"
)
for role, artifact in selected.items():
    (out / f"{role}-artifact-id").write_text(str(artifact["id"]))
PY

for role in ubuntu windows; do
  ARTIFACT_ID=$(cat "$O/$role-artifact-id")
  gh api "repos/$R/actions/artifacts/$ARTIFACT_ID/zip" > "$O/artifacts/$role.zip"
  mkdir -p "$O/artifacts/$role"
  unzip -q "$O/artifacts/$role.zip" -d "$O/artifacts/$role"
  test -f "$O/artifacts/$role/pytest-result.xml"
  test -f "$O/artifacts/$role/pytest-timing.json"
done
HOSTED_ROOT="$O" python /tmp/windows_memory_hosted_audit.py
printf 'HOSTED_ROOT=%s\nNEW_RUN=%s\nATTEMPT=%s\nPR_NUMBER=%s\nSYNTHETIC=%s\n' "$O" "$NEW_RUN" "$ATTEMPT" "$PR_NUMBER" "$SYNTHETIC"
SH
bash -n /tmp/windows_memory_hosted_collect.sh
```

Create the audit parser before running the collector:

```bash
cat > /tmp/windows_memory_hosted_audit.py <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

W = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-resource-memory-probe")
OUTPUT = Path(os.environ["HOSTED_ROOT"])
BASELINE = Path("/tmp/wingman-windows-memory-baseline")
TARGET = "tests/test_fleetsharing_transport_resources.py"
BASE_IDS = [
    TARGET + "::test_maximum_put_uses_actual_default_escaping_under_512k",
    TARGET + "::test_memory_probe_falls_back_without_resource",
    TARGET + "::test_maximum_legal_response_actual_reader_and_codec_in_subprocess",
]
SUFFIX = [
    TARGET + "::test_windows_memory_probe_reports_peak_working_set_without_tracing",
    TARGET + "::test_windows_memory_probe_fails_closed_and_restores_crossings",
]
EXPECTED_TARGET = BASE_IDS + SUFFIX
RESOURCE_ID = BASE_IDS[-1]
ALLOWED = {
    "docs/superpowers/specs/2026-09-24-windows-resource-memory-probe-design.md",
    "docs/superpowers/plans/2026-09-24-windows-resource-memory-probe.md",
    "docs/ci-windows-resource-memory-probe-results.md",
    "docs/ci-test-budget-redesign.md",
    TARGET,
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(case):
    parts = case.get("classname", "").split(".")
    assert len(parts) >= 2 and parts[0] == "tests", parts
    return "::".join(("/".join(parts[:2]) + ".py", *parts[2:], case.get("name", "")))


def normalized_skip(text):
    return re.sub(
        r"pytest-of-[^/\s]+/pytest-\d+/[^\s:\"']+",
        "pytest-of-<USER>/pytest-<N>/<PYTEST_TMP>",
        text.replace("\\", "/"),
    )


def parse(platform):
    root = OUTPUT / "artifacts" / platform
    cases = list(ET.parse(root / "pytest-result.xml").getroot().iter("testcase"))
    ids = [identity(case) for case in cases]
    assert len(ids) == len(set(ids)) == 16609
    counts = defaultdict(int)
    seconds = defaultdict(float)
    skips = []
    failures = errors = 0
    target = []
    for node, case in zip(ids, cases, strict=True):
        duration = float(case.get("time", "0") or 0)
        file_name = node.split("::", 1)[0]
        counts[file_name] += 1
        seconds[file_name] += duration
        skipped = case.find("skipped")
        case_failures = case.findall("failure")
        case_errors = case.findall("error")
        if skipped is not None:
            skips.append(
                (node, normalized_skip(skipped.get("message") or skipped.text or ""))
            )
        failures += len(case_failures)
        errors += len(case_errors)
        if file_name == TARGET:
            target.append(
                {
                    "nodeid": node,
                    "seconds": duration,
                    "outcome": "skipped"
                    if skipped is not None
                    else "failed"
                    if case_failures or case_errors
                    else "passed",
                    "properties": {
                        prop.get("name", ""): prop.get("value", "")
                        for prop in case.findall("./properties/property")
                        if prop.get("name", "").startswith("resource.")
                    },
                }
            )
    timing = json.loads((root / "pytest-timing.json").read_text())
    assert timing["case_count"] == len(ids)
    for file_name, row in timing["files"].items():
        assert row["cases"] == counts[file_name]
        assert abs(row["seconds"] - seconds[file_name]) < 1e-9
    assert failures == errors == 0
    baseline_target = (
        (BASELINE / "target-3.txt").read_text(encoding="utf-8").splitlines()
    )
    baseline_complete = (
        (BASELINE / "complete-16607.txt").read_text(encoding="utf-8").splitlines()
    )
    anchor = baseline_complete.index(baseline_target[-1]) + 1
    expected_complete = [
        *baseline_complete[:anchor],
        *SUFFIX,
        *baseline_complete[anchor:],
    ]
    assert ids == expected_complete
    assert [row["nodeid"] for row in target] == EXPECTED_TARGET
    assert all(row["outcome"] == "passed" for row in target)
    assert all(
        next(row for row in target if row["nodeid"] == node)["outcome"] == "passed"
        for node in SUFFIX
    )
    assert not any(row["nodeid"] in SUFFIX and row["properties"] for row in target)
    resource = next(row for row in target if row["nodeid"] == RESOURCE_ID)
    assert set(resource["properties"]) == {
        "resource.subprocess_wall_seconds",
        "resource.memory_metric",
        "resource.memory_peak",
        "resource.raw_bytes",
        "resource.rows",
        "resource.observations",
    }
    assert resource["properties"]["resource.raw_bytes"] == "47022137"
    assert resource["properties"]["resource.rows"] == "8192"
    assert resource["properties"]["resource.observations"] == "155648"
    assert float(resource["properties"]["resource.subprocess_wall_seconds"]) <= 75
    assert int(resource["properties"]["resource.memory_peak"]) > 0
    expected_metric = {
        "ubuntu": "process_peak_rss_kib",
        "windows": "process_peak_working_set_bytes",
    }[platform]
    assert resource["properties"]["resource.memory_metric"] == expected_metric
    expected_skips = json.loads(
        (BASELINE / f"{platform}-skips.json").read_text(encoding="utf-8")
    )
    assert [list(row) for row in skips] == expected_skips
    assert len(skips) == {"ubuntu": 14, "windows": 67}[platform]
    passed = len(ids) - len(skips)
    assert passed == {"ubuntu": 16595, "windows": 16542}[platform]
    for node, reason in skips:
        lowered = reason.casefold()
        assert not any(
            fragment in lowered
            for fragment in (
                "node is not installed",
                "settings codec not built",
                "codec is not available",
                "k32getprocessmemoryinfo",
                "resource unavailable",
            )
        ), (node, reason)
    return {
        "cases": len(ids),
        "complete_ids": ids,
        "complete_sha256": digest(("\n".join(ids) + "\n").encode()),
        "passed": passed,
        "skips": skips,
        "target": target,
        "target_seconds": seconds[TARGET],
        "resource": resource,
        "xml_sha256": digest((root / "pytest-result.xml").read_bytes()),
        "timing_sha256": digest((root / "pytest-timing.json").read_bytes()),
    }


def changed(left, right):
    return set(
        subprocess.check_output(
            ["git", "-C", str(W), "diff", "--name-only", f"{left}..{right}"],
            text=True,
        ).splitlines()
    )


def job_seconds(job):
    start = datetime.fromisoformat(job["started_at"])
    end = datetime.fromisoformat(job["completed_at"])
    return (end - start).total_seconds()


def step_seconds(job, name):
    row = next(step for step in job["steps"] if step["name"] == name)
    start = datetime.fromisoformat(row["started_at"])
    end = datetime.fromisoformat(row["completed_at"])
    return (end - start).total_seconds()


metadata = json.loads((OUTPUT / "selected.json").read_text())
run = json.loads((OUTPUT / "run.json").read_text())
pr = json.loads((OUTPUT / "pr.json").read_text())
assert metadata["run_id"] == run["id"]
assert metadata["head"] == run["head_sha"] == pr["headRefOid"]
assert metadata["base"] == pr["baseRefOid"]
parents = subprocess.check_output(
    [
        "git",
        "-C",
        str(W),
        "rev-list",
        "--parents",
        "-n",
        "1",
        metadata["synthetic_merge"],
    ],
    text=True,
).split()
assert parents == [metadata["synthetic_merge"], metadata["base"], metadata["head"]]
assert changed(metadata["base"], metadata["head"]) == ALLOWED
assert changed(metadata["base"], metadata["synthetic_merge"]) == ALLOWED
platforms = {platform: parse(platform) for platform in ("ubuntu", "windows")}
assert platforms["ubuntu"]["complete_ids"] == platforms["windows"]["complete_ids"]
assert platforms["ubuntu"]["complete_sha256"] == platforms["windows"]["complete_sha256"]
assert [row["nodeid"] for row in platforms["ubuntu"]["target"]] == [
    row["nodeid"] for row in platforms["windows"]["target"]
]
for platform in ("ubuntu", "windows"):
    archive = OUTPUT / "artifacts" / f"{platform}.zip"
    extracted = OUTPUT / "artifacts" / platform
    expected_digest = metadata["artifacts"][platform]["digest"]
    assert expected_digest == "sha256:" + digest(archive.read_bytes())
    with zipfile.ZipFile(archive) as package:
        assert set(package.namelist()) == {"pytest-result.xml", "pytest-timing.json"}
        for name in package.namelist():
            assert package.read(name) == (extracted / name).read_bytes()
    (OUTPUT / f"{platform}-complete-16609.txt").write_text(
        "\n".join(platforms[platform]["complete_ids"]) + "\n", encoding="utf-8"
    )
logs = {
    role: (OUTPUT / "logs" / f"{role}.log").read_text(errors="replace")
    for role in ("checks", "ubuntu", "windows")
}
assert "platform win32 -- Python" in logs["windows"]
assert "process_peak_working_set_bytes" in logs["windows"]
assert "traced_peak_bytes" not in "\n".join(
    line
    for line in logs["windows"].splitlines()
    if "test_maximum_legal_response_actual_reader_and_codec_in_subprocess" in line
    or "resource.memory_metric" in line
)
assert "platform linux -- Python" in logs["ubuntu"]
assert "process_peak_rss_kib" in logs["ubuntu"]
assert "requires tracemalloc to be disabled" not in logs["windows"]
report = {
    "provenance": metadata,
    "platforms": platforms,
    "paths": sorted(ALLOWED),
    "jobs": {
        role: {
            "job_id": job["id"],
            "job_seconds": job_seconds(job),
            "test_step_seconds": step_seconds(job, "Test")
            if role != "checks"
            else None,
        }
        for role, job in metadata["jobs"].items()
    },
    "claim": "structural instrumentation change only; no speedup attribution",
}
(OUTPUT / "hosted-audit.json").write_text(
    json.dumps(report, sort_keys=True, indent=2) + "\n"
)
print(json.dumps(report, sort_keys=True))
PY
python -m py_compile /tmp/windows_memory_hosted_audit.py
```

---

### Task 5: Polish, Final Review, Publication Stop, and Authorized Hosted Acceptance

**Files:**
- Modify: `docs/ci-windows-resource-memory-probe-results.md`
- Review: all five allowed paths
- Hosted read: authorized run logs/artifacts only after explicit approval

**Interfaces:**
- Consumes: Task 4 locally verified five-path tranche.
- Produces: polished executable head, final change explanation, explicit pre-publication stop, and—after authorization—hosted Windows/Ubuntu evidence at exact 16,609 identities with evidence-head/final-head checks.

- [ ] **Step 1: Run `polish-core --fix` on the complete tranche**

Invoke `polish-core --fix` against `cc48c887..HEAD`. Inspect every edit; retain only high-confidence fixes within the five-path allowlist. If polish proposes a sixth path, product/workflow/summarizer/timing/dependency change, reject it and stop for design review if the issue is correctness-critical.

- [ ] **Step 2: Re-run fresh verification after polish**

At minimum rerun:

```bash
uv run --no-sync python -m pytest \
  tests/test_fleetsharing_transport_resources.py -q -rs --durations=0 \
  --junitxml=/tmp/windows-memory-polished-target.xml
uv run --no-sync python /tmp/windows_memory_endpoint.py
node scripts/js_smoke.js
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
git diff --check cc48c887..HEAD
```

If polish touched executable code, rerun the full Task 4 suite command and complete mutation catalog. Expected endpoint remains `5/4/1/16609`.

- [ ] **Step 3: Run final independent review and resolve findings**

Use a fresh reviewer against the approved spec, this plan, full `cc48c887..HEAD` diff, results ledger, local JUnit/timing JSON, and mutation logs. Require explicit findings for ABI, failure behavior, tracing ownership, crossing restoration/counts, parent ordering, maximum contract, compatibility, scope, and claim discipline. Resolve all valid findings and rerun affected checks.

- [ ] **Step 4: Run `change-explainer` and record the reviewer-facing summary**

Invoke `change-explainer` after fresh verification. Add its concise explanation to the results ledger: what changed, how the native probe works, why no fallback exists, how exact-one crossings and zero-property rejection work, key edge cases, verification actually run, and reviewer focus. Do not include runtime improvement attribution.

- [ ] **Step 5: Commit the polished local executable head**

If polish/review changed executable code or docs, commit within this task using a focused message such as:

```bash
git add docs/ci-windows-resource-memory-probe-results.md \
  docs/ci-test-budget-redesign.md \
  tests/test_fleetsharing_transport_resources.py
git commit -m "test: polish Windows resource memory evidence"
```

If there are no changes, do not create an empty commit.

- [ ] **Step 6: Enforce the pre-authorization publication stop**

Record this exact decision in the results ledger and stop:

```text
PRE-AUTHORIZATION STOP: do not push, create or update a pull request, dispatch or rerun GitHub Actions, download a new-run artifact, or make a hosted acceptance claim until the maintainer explicitly authorizes publication of the verified executable head.
```

The current planning request does not authorize any of those actions.

- [ ] **Step 7: After explicit authorization, verify the PR and executable head before push**

Run `gh pr view` and `git log` as required by repository policy. Confirm the PR targets `elboaf/FlyGD-Wingman` `main`, the exact executable head is the one being published, and no reviewed PR is already merged. Push only after authorization; never use `--no-verify`.

- [ ] **Step 8: Collect the authorized hosted run with explicit inputs**

Generate and compile both Block D scripts verbatim, then run:

Record the two authorized numeric values in the shell, then run:

```bash
read -r NEW_RUN PR_NUMBER
export NEW_RUN PR_NUMBER
bash /tmp/windows_memory_hosted_collect.sh
```

Enter exactly the workflow-run ID and pull-request number from the authorization message, separated by one space. The script rejects absent values and never infers “latest”; copy the literal numeric inputs into the results ledger before execution.

Expected acceptance:

- run/event/attempt/current jobs all successful;
- logs-primary synthetic/head/base agree across all three jobs;
- empty `run.pull_requests` is recorded as `absent`, while explicit PR/run and current PR head/base remain authoritative;
- synthetic parents are exact base/head;
- exactly five synthetic diff paths, matching the allowlist;
- Ubuntu and Windows each contain the exact complete ordered inventory obtained by inserting the two suffix IDs after the baseline target anchor; all 16,607 baseline IDs retain relative order, exact additions/removals are `+2/0`, both platform inventories and SHA-256 hashes agree, and each complete inventory is written to the hosted evidence root;
- Ubuntu `16,595 passed + 14 skipped` with normalized skip tuples exactly equal to the Task 1 Ubuntu baseline; Windows `16,542 passed + 67 skipped` with tuples exactly equal to its Task 1 Windows baseline;
- target module order is exact baseline three plus exact suffix two, all five outcomes are `passed`, ordinary/resource counts are `4/1`, and both new native IDs are explicitly passed rather than inferred from absence of failure;
- Windows resource metric `process_peak_working_set_bytes`; Ubuntu `process_peak_rss_kib`;
- Windows log has no resource `traced_peak_bytes`, no trace-active failure, and no native availability skip;
- six properties and maximum bytes/rows/observations/read/closure/exact-one crossings remain accepted;
- wall at or below `75`, subprocess timeout unchanged at `300`;
- artifact digest matches API digest; JUnit/timing file counts and sums agree;
- job duration, Test-step duration, target testcase durations, and resource child wall are recorded as observations only.

- [ ] **Step 9: Update results with hosted evidence and commit the evidence head**

Append exact run/attempt/PR, synthetic/head/base, job IDs, artifact IDs/digests, Python/platform provenance, identity hashes, normalized skip tuples, six properties, target/test/job timings, five-path diff, and all Block D assertions to the results ledger. State only the approved structural claim.

Commit:

```bash
git add docs/ci-windows-resource-memory-probe-results.md
git commit -m "docs: record hosted Windows memory probe evidence"
```

- [ ] **Step 10: Push the evidence head only if separately authorized, then verify required checks**

After authorization, push the evidence commit and wait for exact required statuses `checks`, `test (ubuntu-latest)`, and `test (windows-latest)`. Record their run/job IDs in a final status-closing results edit. This evidence-head run is status evidence only; the prior executable-head run remains behavior/timing authority.

- [ ] **Step 11: Commit and, if authorized, push the status-closing final head**

Commit only the results ledger:

```bash
git add docs/ci-windows-resource-memory-probe-results.md
git commit -m "docs: close Windows memory probe verification"
```

If authorized, push and verify all three required checks on this final head. Report final-head check URLs/IDs in the completion handoff rather than creating a recursive documentation commit.

- [ ] **Step 12: Final completion report**

Return:

- exact plan/implementation/evidence/final commit SHAs and subjects;
- every focused/full/tool/hosted check actually run and literal outcome;
- exact hosted provenance, jobs, artifacts, skips, properties, and observations;
- exact five committed paths and protected-path audit;
- structural instrumentation conclusion only;
- remaining concerns, including single-sample timing noise and the fact that native process-lifetime peak working set is not comparable to the old traced-allocation peak.

---

## Adaptation and Stopping Rules

Stop and return to design review rather than adapting silently if any of these occurs:

1. `K32GetProcessMemoryInfo` is unavailable from `kernel32` on hosted Windows.
2. Windows appears to need `resource` or tracing fallback.
3. Exact natural layout cannot be represented for 32-bit and 64-bit pointer widths.
4. More than two identities or any existing identity change is required.
5. The maximum bytes, rows, observations, read amount, closure, client, decoder/parser exact-one crossings, timeout, budget, or six-property schema must change.
6. The parent cannot gate the metric immediately after JSON parse with zero properties on rejection.
7. Any production, workflow, summarizer, timing-test, dependency, configuration, marker, selector, budget, shard, historical-document, or sixth-path change is required.
8. Hosted Windows can pass only by skipping the native crossing.
9. Evidence supports only a memory ceiling/delta or speedup claim rather than the approved structural no-test-owned-tracing claim.

## Plan Self-Review Checklist

Before committing this plan, verify:

- all approved spec requirements map to Tasks 1–5;
- exact two suffix names/order appear consistently in code, audits, and hosted parser;
- target arithmetic is `3 -> 4 -> 5`; suite arithmetic is `16,607 -> 16,608 -> 16,609`;
- final local outcome is `16,595 passed + 14 skipped`; hosted Windows projection is `16,542 passed + 67 skipped`;
- structure fields/types/order, offset formula, size formula, alignment, signatures, handle, `cb`, fresh samples, no pack, no `ctypes.wintypes`, and no close are explicit;
- value evidence distinguishes peak, current, pagefile, signed/narrower truncation, and native widths;
- loader, each named export, zero return, explicit last-error/WinError seams, exact saved-error call tuple, no fallback, and no trace start/stop are explicit;
- the actual `sys.modules["tracemalloc"]` fake spans setup/sampling/cleanup, real-import start/stop mutants are killed, and an actual `PYTHONTRACEMALLOC=1` child fails before payload/decode with empty stdout;
- active trace, exact/equivalent-object crossing restoration, original sentinel, and no failed-operation success-count claim are explicit;
- maximum rows/generated observations/raw/read/closure/decoder/parser/budget/child-wrong-metric mutations are exact and restoration-safe;
- interim, final, local, and hosted audits compare complete ordered inventories, exact additions/removals, target outcomes, baseline-relative order, complete hashes, and platform-local normalized skip tuples;
- the mutation runner aggregates every command/regex failure, returns nonzero on any failure, and verifies exact bytes/hash/binary-diff/status restoration in `finally`;
- parent ordering and zero-property rejection are explicit;
- all scripts are self-contained and have compile or shell-syntax checks;
- no changes to timing tests, summarizer, workflow, product, dependencies, configuration, markers, selectors, budgets, shards, or historical evidence are planned;
- exact five-path allowlist and synthetic diff are enforced;
- hosted collector handles empty `pull_requests` with explicit PR/run and logs-primary provenance;
- publication stop, evidence-head checks, and final-head checks are explicit;
- no unfinished implementation marker or omitted-body instruction remains;
- no speedup attribution appears.
