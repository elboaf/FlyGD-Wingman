# Broad CI Waste Reduction — Stage A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not dispatch subagents unless the maintainer separately authorizes them.

**Goal:** Remove deterministic same-identity waste from four Preview readiness transitions, one 2,101-prefix timing oracle, and eight screenshot walks while preserving all 16,609 ordered identities and every production/workflow contract.

**Architecture:** Stage A is test architecture only. A test-local Preview observer atomically wraps the callback that `Api` actually installed; the rolling timing case independently limits only its oracle input; screenshot tests select original production `Screen` objects and share one immutable module-lifetime failure receipt. Production code, shipped helpers, inventories, workflows, dependencies, cadence, selectors, markers, fixtures, and public interfaces remain unchanged.

**Tech Stack:** Python 3.11, pytest 9, stdlib `ast`/`dataclasses`/`hashlib`/`json`/`random`/`subprocess`/`threading`/`types`/`xml.etree.ElementTree`/`zipfile`, uv, Ruff, Node.js, Cargo, Git, GitHub CLI, and GitHub Actions JUnit/timing artifacts.

**Spec:** `docs/superpowers/specs/2026-09-26-ci-broad-waste-reduction-stage-a-design.md`

**Execution status:** Tasks 1–4 and Task 5's local Steps 1–7 are complete.
The frozen reviewed executable head is
`83bd018b6eeb29e159741258e8d979c7481d7d01`; the final local commit records
approved documentation evidence only. The maintainer's exact later statement
`authorize remaining steps` satisfies the publication authorization gate, but
Steps 8–10 remain deliberately unexecuted until parent final review as required
by the current instruction. The procedural checkboxes in Tasks 1–4 below are
retained as the original execution recipe; the cumulative results ledger is the
authoritative completion record.

## Global Constraints

- Source baseline is merged `main` commit `463bccb07077325e64b6ad7f7ce4e9c100d2fcd6` (`Stop Fleet source bootstrap at accepted readiness (#290)`).
- Hosted reference is PR #290 run `36208309831`, attempt `1`, executable head `3523dd0873493c8ecac0599b7c2daaf4d44d5902`, synthetic merge `26428a687ad24f99cb21f8ff9f18628023c71799`, and base `f6e8ecd5b09889e79aa169ce103b2eb9681cec9f`.
- Preserve exactly 16,609 unique ordered identities with final-newline SHA-256 `f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100`.
- Preserve Ubuntu `16,595 passed + 14 skipped` and Windows `16,542 passed + 67 skipped`; normalized ordered skip hashes remain Ubuntu `14f1511f840fb2fdc1680123dde29a7143405829af97141d62c5099aa4f265af` and Windows `41a767f45f49215310104dc611a4e9b60e4cb251e90f850b80a6f3b1cd9bcfb6`.
- Preserve all names, parameters, IDs, decorators, markers, order, cadence, workflow selectors, shards, timeout values, release gates, dependencies, configuration, and packaging. Preserve every test signature except the four exact screenshot receipt-consumer substitutions listed below.
- Exact versioned tranche scope is eight total paths only—spec + plan + results + five tests:
  - `docs/superpowers/specs/2026-09-26-ci-broad-waste-reduction-stage-a-design.md`;
  - this plan;
  - `docs/ci-broad-waste-reduction-stage-a-results.md`;
  - `tests/test_preview_runtime_review.py`;
  - `tests/test_preview_presentation.py`;
  - `tests/test_preview_geometry_publication.py`;
  - `tests/test_fleetsharing_timing.py`;
  - `tests/test_shoot_screens.py`.
- User authorization covers versioning the Stage A spec, plan, results, and evidence. The later exact statement `authorize remaining steps` also covers the remaining publication and hosted-evidence sequence; the current instruction nevertheless holds all remote action until parent final review. Stage B/C and unrelated Superpowers artifacts remain unauthorized.
- No permanent file under `wingman/`, `.github/`, `packaging/`, `scripts/`, `tests/fixtures/`, `tests/test_new_screenshots.py`, or `tests/test_current_screenshots.py` changes.
- Node on `PATH` and the built release settings codec in `packaging/bin` remain mandatory complete-suite prerequisites. Node/codec/unexpected native-availability skips invalidate acceptance.
- The Preview bound and every supplied predicate remain literal five seconds and byte-for-behavior unchanged. `eve_on()` remains byte-for-byte unchanged.
- The rolling case retains exactly 2,101 candidates, 2,101 commits, exact vectors/intervals, detached-before-commit identity, `<= 96`, final `2202100`, and clear inconsistency latch. `diagnostic_oracle()` remains unchanged.
- Production `shoot.walk()` and all 61 `shoot.SCREENS` remain unchanged. One retained test traverses all 61 and separately asserts exact keys and every `error is None`.
- Every temporary edit is match-once, records original bytes/SHA-256 plus `git diff --binary HEAD -- .` and NUL-delimited `git status --porcelain=v2 --untracked-files=all -z`, restores all four exactly, and stops immediately on mismatch.
- TDD RED evidence is never committed. Intermediate commits contain green tests only.
- `20.275s`, `13.320s`, `8.907s`, `42.502s`, `646.538s`, and `680s` are observations only. `42.502s` is the affected testcase upper sum—not a projected saving, lower bound, p95, Test-step, job, throughput, or critical-path claim.
- Stage B persistent workers/saved-layout receipt bundling and Stage C deletion/consolidation (including the approximate 346 discovery candidates) are explicitly excluded.

---

## File Structure and Ownership

### Created during execution

- `docs/ci-broad-waste-reduction-stage-a-results.md` — exact baseline provenance, identity/skip ledgers, structural counts, RED/GREEN evidence, mutation outcomes, order runs, complete local endpoint, reviews, publication stop, and any separately authorized hosted evidence.

### Modified during execution

- `tests/test_preview_runtime_review.py` — two-mode wait seam plus test-local trigger observer; `eve_on()` is untouched.
- `tests/test_preview_presentation.py` — only the trigger-helper import and two named post-`main_api()` EVE conversions.
- `tests/test_preview_geometry_publication.py` — only the trigger-helper import, retained-drag EVE conversion, and companions `[True]` conversion.
- `tests/test_fleetsharing_timing.py` — only the rolling case's independently bounded oracle input.
- `tests/test_shoot_screens.py` — frozen production-key selector, exact full traversal assertions, focused selectors, immutable Preview failure receipt, and existing-identity assertion strengthening.

### Read-only authorities

- `wingman/preview/runtime.py`, `wingman/ui/api.py`, `wingman/ui/fleetpresentation.py`, `wingman/fleetsharing/timing.py`, `scripts/shoot_screens.py`.
- `tests/preview_runtime_helpers.py`, `tests/test_preview_layout_batch.py`, `tests/test_new_screenshots.py`, `tests/test_current_screenshots.py`.
- `docs/ci-test-strategy-design.md`, `docs/ci-test-strategy-phase-1-results.md`, `docs/ci-test-budget-redesign.md`, `docs/ci-test-budget-fleet-tranche-results.md`, completed screenshot/setup/resource/readiness designs and results, and `/mnt/c/dev/flygd-wingman/tmp/next-hotspot-36208309831`.

## Frozen Identity and Hash Ledger

All hashes below are SHA-256 over exact ordered node IDs joined with `"\n"` and one final newline.

| Selection | Count | Ordered hash |
|---|---:|---|
| complete `tests/` | 16,609 | `f468ba1954d3ff0ab693dd721ff8a7a4d12266e16d8568035de4245a6c616100` |
| five in-scope test files | 313 | `a21d48abcdfaeb9b2b33ab5e1b089f5da4e692f01bebe94c104908728235eaef` |
| relevant changed/consumer selection | 494 | `ad677b5f7f9b2667401ccfc39295de021c8a320498d59a3679b05497491b229e` |
| eight `runtime_pump` consumer files | 388 | `36e61c70b9d081f2302bd2928f2b83e2c8d6e9032fe2c9fa8dd0c2eeee0d784f` |
| `test_preview_runtime_review.py` | 20 | `dfb34888c52b3db0c6b70b35ae033b7a45e9a77c75e6e29448d86a43ef50691e` |
| `test_preview_presentation.py` | 15 | `582d30ccfa1102d8128fe9e365abccfa9bd2181be752096e576c6a3fe4701df2` |
| `test_preview_geometry_publication.py` | 17 | `95840e2f840134c3ac38e7c055c69f4fdff72724e81500780c49ddc7959ae76f` |
| `test_fleetsharing_timing.py` | 41 | `f4fe35e78a92078c923fd894382c38924501fe6d1f3a4e56a8f8839c0382e37a` |
| `test_shoot_screens.py` | 220 | `156563ca03eb0f29c887f26e6aea18e393d54e7793a6a0a5fe557250cc406e81` |
| `test_new_screenshots.py` | 90 | `c885cb48a3fbc03547291ff302a079cff2d5ebe42c7faeb5c4ec0a5e40a2938d` |
| `test_current_screenshots.py` | 91 | `c0a709d70a349ef901ec28a86be422bcf17dddb2c6cc75beec3c39544010ef8b` |
| four Preview hotspot IDs | 4 | `97886a5121cd3ecb1be6c2f3b9b6c4d423274dadd9f9fbb055006fd7c773b2eb` |
| rolling timing ID | 1 | `7315dfab22e06d84f2c7b818e2ceb488e4c5667f13b2e8e50f37e3abb39b915e` |
| eight changed screenshot IDs | 8 | `d42ecdf5d0c82bdd29e86f43c9553eefee50dfdd8fceee1e65430dad589c9774` |
| contiguous `test_shoot_screens.py` target block | 15 | `628e82704990f6186c5d1b2d213308d99cf9f77a9ac42925c7404f213ca476c5` |
| unchanged new-screenshot block | 8 | `cd7c178e1482a5e04aa5bc3727d15e72f7fc3a91866d18c423dd54f4ab5eda99` |
| unchanged current-screenshot block | 12 | `b1f7e96d4322dd13a9d2023635a02881fdc9edee7955eb4717f98ff879517cac` |
| 35 screenshot IDs, normal | 35 | `75e7172a2c9685582b2e4adbc15decd71bc2ebb978f65b84acf9f738c2546786` |
| 35, reverse only inside 15-ID block | 35 | `dfef25628da7c26bd98db8f4fc5862bd5dc2c7c73888b92197fd1279bf8c4ef1` |
| 35, seed-`20260926` shuffle only inside 15-ID block | 35 | `04a1f9125d3bbbb0dbef9eed72916b8a11db8d0b6cbc08782f084f50d6a5e59f` |

Protected baseline byte hashes:

```text
adde9c49b469fbffe7816c746da7078fbfcc88aada9412ad318193c3072101c0  wingman/preview/runtime.py
730298e68701348ce175d4db3fd75ac95c343b939d07052e0ea3d772a17615ce  wingman/ui/api.py
db714251d8744ecdb0862414126baf2aa887578af4f7c6919520e32e00246613  wingman/ui/fleetpresentation.py
0b09ec89d47b803089015a6e21f80604219ec1b619909ca400e5e7e7d9520901  wingman/fleetsharing/timing.py
05e03a76374d16719568eb92b461ef1b50a7e5ff35ef2cd3944b97aa3d4453b4  scripts/shoot_screens.py
ffb2024c3931ab599c3e33cb9a1bbc4188224392fc1caadf58e989c58b29e157  tests/test_new_screenshots.py
1a6dabb9d2e6f8360268eab5045334d25c4ad09048ca99bfc166d80edf6bb021  tests/test_current_screenshots.py
18c39a550a941d8fdb06af6d0764e31e19fd01fe9616ecf3785ebdf158d33b3a  tests/preview_runtime_helpers.py
2ff792554c2aff31664854ab9aa68968be8aa4b1e4842ec4ae670893015e4285  tests/test_preview_layout_batch.py
9524b760b9f74c09b39c7d096cf1e1494b16e6607e8a5c7422d97e9ee4811222  .github/workflows/ci.yml
33620c99049ad82b1366b2c63cf9957ebb9ea928e08445b9ea8fefd28c789412  pyproject.toml
ebf5e1a5e892dd6488385d117c64a14dd0b0575ef9dbc4565b07a3012f9ad499  uv.lock
c6668b09f3fd3aaff0af1ca3a7dbaa77a40d7c349b06c2f42038134e094fa101  packaging/settings-codec/Cargo.toml
```

The exact unchanged `eve_on()` source and hash are:

```python
def eve_on(r, revision=1):
    r.runtime.set_eve(True, revision)
    r.wait_state(lambda state: state.eve == "active")
```

```text
685f6f1b8950c70c811b3eebc0213ad1bf547488acc214a207ef4b9cd6526f47
```

## Exact Target Node IDs

### Preview four

```text
tests/test_preview_presentation.py::test_main_adapters_never_present_on_pump_and_coalesce_while_page_blocked
tests/test_preview_presentation.py::test_identified_capture_through_main_while_old_delivery_is_blocked
tests/test_preview_geometry_publication.py::test_retained_drag_and_commit_notify_distinct_authorities
tests/test_preview_geometry_publication.py::test_off_apply_refreshes_retained_geometry_without_eve_start[True]
```

### Rolling timing one

```text
tests/test_fleetsharing_timing.py::test_rolling_diagnostic_allows_legal_one_ms_per_second_drift_for_2101_prefixes
```

### Eight changed screenshot identities

```text
tests/test_shoot_screens.py::test_walk_records_setup_failure_as_failed_shot
tests/test_shoot_screens.py::test_walk_applies_and_clears_device_metrics_for_narrow_screen
tests/test_shoot_screens.py::test_walk_clears_device_metrics_even_when_narrow_screenshot_fails
tests/test_shoot_screens.py::test_walk_applies_device_metrics_before_narrow_setup_script
tests/test_shoot_screens.py::test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure
tests/test_shoot_screens.py::test_walk_failure_path_records_set_eval_attempt_clear_in_order
tests/test_shoot_screens.py::test_walk_failure_path_records_attempt_before_clear_not_only_clear
tests/test_shoot_screens.py::test_walk_injects_fittings_fixture_before_stage_actions
```

### Fifteen contiguous `test_shoot_screens.py` IDs

```text
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[settings-wanderer-controls-narrow]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[profiles-copy-scope]
tests/test_shoot_screens.py::test_gap_capture_walk_settles_then_verifies_and_reports_fixture[fittings-copy-preflight-bottom-narrow]
tests/test_shoot_screens.py::test_walk_records_setup_failure_as_failed_shot
tests/test_shoot_screens.py::test_walk_applies_and_clears_device_metrics_for_narrow_screen
tests/test_shoot_screens.py::test_walk_clears_device_metrics_even_when_narrow_screenshot_fails
tests/test_shoot_screens.py::test_walk_applies_device_metrics_before_narrow_setup_script
tests/test_shoot_screens.py::test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure
tests/test_shoot_screens.py::test_walk_failure_path_records_set_eval_attempt_clear_in_order
tests/test_shoot_screens.py::test_walk_failure_path_records_attempt_before_clear_not_only_clear
tests/test_shoot_screens.py::test_walk_injects_fittings_fixture_before_stage_actions
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[fittings-copy-progress]
tests/test_shoot_screens.py::test_walk_refuses_capture_when_postcondition_fails[settings-previews-groups]
tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure[False]
tests/test_shoot_screens.py::test_alerts_base_capture_walk_waits_then_frames_or_records_failure[True]
```

### Eight unchanged `test_new_screenshots.py` IDs

```text
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-prepare]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-stage]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-verify]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[profiles-setup-import-capture]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-prepare]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-stage]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-verify]
tests/test_new_screenshots.py::test_new_capture_cleanup_runs_after_any_failure[settings-previews-crop-narrow-capture]
```

### Twelve unchanged `test_current_screenshots.py` IDs

```text
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[None-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[prepare-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[entry-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[stage-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[verify-settings-fleet-sharing-history-narrow]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-companions-populated]
tests/test_current_screenshots.py::test_current_walk_prepares_before_entry_and_always_cleans[capture-settings-fleet-sharing-history-narrow]
```

### Exact screenshot key contracts

```python
_EXPECTED_FULL_SCREEN_KEYS = (
    "uploader",
    "settings-uploading",
    "settings-uploading-recording",
    "settings-uploading-integrations",
    "settings-uploading-webhook",
    "settings-companions",
    "settings-companions-populated",
    "settings-companions-detail-narrow",
    "settings-companions-add",
    "settings-companions-source-narrow",
    "settings-characters",
    "settings-characters-waiting",
    "settings-characters-partial-cleanup",
    "settings-characters-narrow",
    "settings-bookmarks",
    "settings-bookmarks-windows",
    "settings-bookmarks-sigbar",
    "settings-previews",
    "settings-previews-middle",
    "settings-previews-table",
    "settings-previews-sticky-conflict",
    "settings-previews-detail",
    "settings-previews-copy",
    "settings-previews-groups",
    "settings-previews-narrow",
    "settings-previews-crop-narrow",
    "settings-wanderer",
    "settings-wanderer-narrow",
    "settings-wanderer-controls-narrow",
    "settings-fleet",
    "settings-fleet-characters-narrow",
    "settings-fleet-sharing",
    "settings-fleet-sharing-details",
    "settings-fleet-sharing-history-narrow",
    "settings-alerts",
    "settings-alerts-advanced",
    "settings-alerts-custom-narrow",
    "settings-general",
    "profiles",
    "profiles-copy-scope",
    "profiles-account-identity",
    "profiles-backups",
    "profiles-formations",
    "profiles-formations-import",
    "profiles-setup-share",
    "profiles-setup-import",
    "skills",
    "fittings",
    "fittings-unfiled",
    "fittings-superseded",
    "fittings-alliance",
    "fittings-detail",
    "fittings-metadata-narrow",
    "fittings-narrow",
    "fittings-copy-preflight",
    "fittings-copy-preflight-bottom-narrow",
    "fittings-copy-limit",
    "fittings-copy-progress",
    "fittings-copy-result",
    "fittings-copy-result-bottom-narrow",
    "dialog",
)

_EXPECTED_FITTINGS_KEYS = (
    "fittings",
    "fittings-unfiled",
    "fittings-superseded",
    "fittings-alliance",
    "fittings-detail",
    "fittings-metadata-narrow",
    "fittings-narrow",
    "fittings-copy-preflight",
    "fittings-copy-preflight-bottom-narrow",
    "fittings-copy-limit",
    "fittings-copy-progress",
    "fittings-copy-result",
    "fittings-copy-result-bottom-narrow",
)
```

---

## Reproducibility Protocol

### Identity/JUnit parser

Use this module for collection, JUnit order, per-ID failure ownership, and masking rejection. It resolves nested repository test classes by the longest existing module prefix. External `/tmp/test_stage_a_preview_observer.py` cases have a one-component classname, so their collection plugin must supply an exact `(classname, item.name) -> item.nodeid` map; guessing a path from JUnit is forbidden.

```python
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-broad-waste-stage-a")


def ordered_hash(nodes: list[str]) -> str:
    return hashlib.sha256(("\n".join(nodes) + "\n").encode()).hexdigest()


def skip_payload(pairs: list[list[str]]) -> bytes:
    # This exact serialization defines both normalized platform skip hashes.
    return (json.dumps(pairs, indent=2) + "\n").encode("utf-8")


def load_exact_id_map(path: Path) -> dict[tuple[str, str], str]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    mapping = {}
    nodeids = []
    for row in rows:
        key = (str(row["classname"]), str(row["name"]))
        assert key not in mapping, key
        nodeid = str(row["nodeid"])
        mapping[key] = nodeid
        nodeids.append(nodeid)
    assert len(nodeids) == len(set(nodeids)), nodeids
    return mapping


def junit_id(
    case: ET.Element,
    exact_id_map: dict[tuple[str, str], str] | None = None,
) -> str:
    classname = case.get("classname", "")
    name = case.get("name", "")
    key = (classname, name)
    if exact_id_map is not None and key in exact_id_map:
        return exact_id_map[key]
    parts = classname.split(".") if classname else []
    for end in range(len(parts), 0, -1):
        path = "/".join(parts[:end]) + ".py"
        if (ROOT / path).is_file():
            return "::".join((path, *parts[end:], name))
    raise AssertionError(("unmapped JUnit identity", key))


def normalized_skip(text: str) -> str:
    return re.sub(
        r"pytest-of-[^/\s]+/pytest-\d+/[^\s:\"']+",
        "pytest-of-USER/pytest-N/PYTEST_TMP",
        text.replace("\\", "/"),
    )


def parse_junit(
    path: Path,
    exact_id_map: dict[tuple[str, str], str] | None = None,
) -> list[dict[str, object]]:
    rows = []
    for case in ET.parse(path).getroot().iter("testcase"):
        children = [
            child
            for child in case
            if child.tag in ("failure", "error", "skipped")
        ]
        assert len(children) <= 1, case.attrib
        child = children[0] if children else None
        outcome = child.tag if child is not None else "passed"
        rows.append(
            {
                "nodeid": junit_id(case, exact_id_map),
                "outcome": outcome,
                "phase": {
                    "failure": "call",
                    "error": "setup-or-teardown",
                    "skipped": "skip",
                    "passed": "passed",
                }[outcome],
                "type": "" if child is None else (child.get("type") or ""),
                "message": "" if child is None else (child.get("message") or ""),
                "traceback": "" if child is None else (child.text or ""),
                "seconds": float(case.get("time", "0") or 0),
            }
        )
    nodeids = [str(row["nodeid"]) for row in rows]
    assert len(nodeids) == len(set(nodeids)), nodeids
    return rows


def require_intended_failure(
    junit: Path,
    exact_id_map: dict[tuple[str, str], str],
    expected_node: str,
    intended: str,
    forbidden: tuple[str, ...],
) -> None:
    rows = parse_junit(junit, exact_id_map)
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["nodeid"] == expected_node, row
    assert row["outcome"] == "failure" and row["phase"] == "call", row
    detail = str(row["message"]) + "\n" + str(row["traceback"])
    assert re.search(intended, detail), (expected_node, detail)
    assert not any(value in detail for value in forbidden), (expected_node, detail)
```

Materialize `/tmp/stage_a_external_collection_plugin.py` exactly as follows so external IDs are observed rather than reconstructed:

```python
from __future__ import annotations

import json
import os
from pathlib import Path


def pytest_collection_finish(session) -> None:
    rows = [
        {
            "classname": item.module.__name__,
            "name": item.name,
            "nodeid": item.nodeid,
        }
        for item in session.items
    ]
    assert len(rows) == 18, rows
    keys = [(row["classname"], row["name"]) for row in rows]
    nodeids = [row["nodeid"] for row in rows]
    assert len(keys) == len(set(keys))
    assert len(nodeids) == len(set(nodeids))
    Path(os.environ["STAGE_A_EXTERNAL_IDS"]).write_text(
        json.dumps(rows, indent=2) + "\n",
        encoding="utf-8",
    )
```

Before any observer mutation, collect and run all 18 cases through literal files:

```bash
STAGE_A_EXTERNAL_IDS=/tmp/stage-a-observer-ids.json \
PYTHONPATH="$PWD:/tmp" python -m pytest \
  /tmp/test_stage_a_preview_observer.py --collect-only -q \
  -p stage_a_external_collection_plugin
PYTHONPATH="$PWD:/tmp" python -m pytest \
  /tmp/test_stage_a_preview_observer.py -q \
  --junitxml=/tmp/stage-a-observer.xml
```

Load the generated map, require that `parse_junit()` returns those exact collected IDs in order with 18 `passed` outcomes, and reject duplicate/unmapped identities. This is the literal parser self-test for one-component classnames.

For every mutation, an eventual failure is insufficient: each selected JUnit node must be exact, outcome must be call-phase `failure` rather than setup/teardown `error` or `skipped`, the unique sentinel/assertion regex must occur in preserved message plus traceback, and the parser must reject timeout, setup, collection, unrelated callback, competing timing-window, or later generic failures.

### Exact restoration wrapper

Every mutation/instrumentation runner uses this pattern around each target path:

```python
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from types import TracebackType

W = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-broad-waste-stage-a")


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(W), *args])


def mutate_once(path: Path, old: str, new: str, probe) -> None:
    original = path.read_bytes()
    original_sha = hashlib.sha256(original).hexdigest()
    before_diff = git_bytes("diff", "--binary", "HEAD", "--", ".")
    before_status = git_bytes(
        "status", "--porcelain=v2", "--untracked-files=all", "-z"
    )
    text = original.decode("utf-8")
    assert text.count(old) == 1, (path, text.count(old), old)
    probe_error: BaseException | None = None
    probe_tb: TracebackType | None = None
    restoration_error: BaseException | None = None
    try:
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        probe()
    except BaseException as error:  # noqa: BLE001 -- restore before rethrowing probe.
        probe_error = error
        probe_tb = error.__traceback__
    finally:
        try:
            path.write_bytes(original)
            assert path.read_bytes() == original
            assert hashlib.sha256(path.read_bytes()).hexdigest() == original_sha
            assert git_bytes("diff", "--binary", "HEAD", "--", ".") == before_diff
            assert (
                git_bytes(
                    "status", "--porcelain=v2", "--untracked-files=all", "-z"
                )
                == before_status
            )
        except BaseException as error:  # noqa: BLE001 -- restoration must win.
            restoration_error = error
    if restoration_error is not None:
        raise restoration_error from probe_error
    if probe_error is not None:
        raise probe_error.with_traceback(probe_tb)
```

All byte/hash/binary-diff/NUL-status restoration assertions execute inside `finally`, even when the probe itself raises. A successful restoration rethrows the original probe object with its traceback; a restoration mismatch is raised chained from the probe and stops the matrix. Before real mutations, test this wrapper in a disposable temporary Git repository twice: a sentinel probe plus exact restore must rethrow the sentinel after proving clean state, while a deliberately broken restore must raise `RestorationError("restoration bytes mismatch")` with the original sentinel as `__cause__` and must prevent a second probe.

---

### Task 1: Freeze the Merged PR #290 Baseline

**Files:**
- Create: `docs/ci-broad-waste-reduction-stage-a-results.md`
- Read: all authorities and `/mnt/c/dev/flygd-wingman/tmp/next-hotspot-36208309831`
- Temporarily instrument, then restore: none of the versioned files remain changed

**Interfaces:**
- Consumes: merged `463bccb0`, run `36208309831`, the frozen ledgers above, six retained artifact files, and current production/test helpers.
- Produces: committed baseline results with exact identities, outcomes/skips, artifact provenance, four disconnected waits, timing checks/transitions, screenshot walks/visits, and inventory counts.

- [ ] **Step 1: Verify branch/base and documentation-only starting state**

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-broad-waste-stage-a
git status --short --branch
git log -5 --oneline --decorate
git merge-base origin/main HEAD
git merge-base --is-ancestor 463bccb07077325e64b6ad7f7ce4e9c100d2fcd6 HEAD
git diff --check
```

Expected: branch `ci-broad-waste-stage-a`, baseline ancestry exact, and only the approved spec/plan history differs from `origin/main`; no test, production, workflow, or generated artifact is dirty.

- [ ] **Step 2: Verify retained PR #290 artifacts byte-for-byte**

```bash
sha256sum \
  /mnt/c/dev/flygd-wingman/tmp/next-hotspot-36208309831/ubuntu.zip \
  /mnt/c/dev/flygd-wingman/tmp/next-hotspot-36208309831/ubuntu/pytest-result.xml \
  /mnt/c/dev/flygd-wingman/tmp/next-hotspot-36208309831/ubuntu/pytest-timing.json \
  /mnt/c/dev/flygd-wingman/tmp/next-hotspot-36208309831/windows.zip \
  /mnt/c/dev/flygd-wingman/tmp/next-hotspot-36208309831/windows/pytest-result.xml \
  /mnt/c/dev/flygd-wingman/tmp/next-hotspot-36208309831/windows/pytest-timing.json
unzip -l /mnt/c/dev/flygd-wingman/tmp/next-hotspot-36208309831/ubuntu.zip
unzip -l /mnt/c/dev/flygd-wingman/tmp/next-hotspot-36208309831/windows.zip
```

Require exactly:

```text
3670232e32405fd1342e45eef655c7640f8650d5e52dacc29383715196faa15e  ubuntu.zip
44474a56fc90e93d267df3f11318d12acf0a4515bc71e0c9db2f02bfcd0d8d1b  ubuntu/pytest-result.xml
bd208ba1e6a502b553e0f00e7e8914fb925073a21b3329a26d96af447d46d4f7  ubuntu/pytest-timing.json
f7afad089e74456e76e1b3133a0a55c8d5f296c5a557af16b1009e80c6f6300f  windows.zip
1b993ea2dcf7245fceec7fb7213d4212d6a77f94925cc4c7274eaf3d0a62acdb  windows/pytest-result.xml
cde109559e59aa89cc9ddba2dff0c8c796aad77735defd1c7fd62614b9d88c12  windows/pytest-timing.json
```

Each ZIP member set must be exactly `pytest-result.xml` and `pytest-timing.json`; extracted bytes must equal member bytes. Record artifact IDs Ubuntu `10894627359` and Windows `10894793997` and job IDs checks `108309461453`, Ubuntu `108309461358`, Windows `108309461427`.

- [ ] **Step 3: Parse exact identities, outcomes, skips, and timings**

Materialize the Identity/JUnit parser as `/tmp/stage_a_identity.py`; compile/Ruff it. Parse both XMLs and timing JSONs. Require:

- both platform ID arrays equal source collection exactly and hash to the frozen 16,609 hash;
- zero failures/errors, no target skip, no Node/codec/unexpected native skip;
- Ubuntu `16,595/14`, Windows `16,542/67`, exact normalized skip arrays and hashes; construct each array as JSON-compatible `[nodeid, normalized_message]` lists and hash exactly `(json.dumps(pairs, indent=2) + "\n").encode("utf-8")`—no sorting, `ensure_ascii` override, tuple repr, or alternate separators;
- timing JSON `case_count` and each file count/sum agree with XML within `1e-9`;
- Windows testcase sum `646.538s`, XML suite time `675.274s`, Test-step observation `680s`, and job observation `741s` remain distinct measures;
- Ubuntu job/Test observations are `307s/287s`; checks job is `9s`.

Record the four exact Preview observations `5.150 + 5.009 + 5.057 + 5.059 = 20.275s`, rolling `13.320s`, eight screenshot observations summing `8.907s`, and affected upper sum `42.502s`.

- [ ] **Step 4: Collect exact source identities/orders and source shapes**

Use a `pytest_collection_finish` plugin that writes `item.nodeid` and sorted marker names. Collect complete, five-file, 494-case relevant, eight-runtime-consumer, Preview-four, rolling-one, changed-eight, contiguous-15, new-eight, and current-12 selections. Require every count/hash in the Frozen Identity and Hash Ledger.

AST-record every test function signature/decorator in the five in-scope files. Require identical function-name sets, decorators, parameterized IDs, markers, and collected node order. The only allowed signature changes are these four exact substitutions in `tests/test_shoot_screens.py`:

```text
test_walk_clears_device_metrics_even_when_narrow_screenshot_fails:
    (tmp_path, monkeypatch) -> (preview_narrow_failure_walk)
test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure:
    (tmp_path, monkeypatch) -> (preview_narrow_failure_walk)
test_walk_failure_path_records_set_eval_attempt_clear_in_order:
    (tmp_path, monkeypatch) -> (preview_narrow_failure_walk)
test_walk_failure_path_records_attempt_before_clear_not_only_clear:
    (tmp_path, monkeypatch) -> (preview_narrow_failure_walk)
```

For every other `test_*` function require exact `args`, `posonlyargs`, `kwonlyargs`, `vararg`, `kwarg`, and decorator AST equality. The endpoint identity script includes this explicit exception gate:

```python
ALLOWED_SIGNATURES = {
    "test_walk_clears_device_metrics_even_when_narrow_screenshot_fails",
    "test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure",
    "test_walk_failure_path_records_set_eval_attempt_clear_in_order",
    "test_walk_failure_path_records_attempt_before_clear_not_only_clear",
}
changed = set()
for key in baseline_shapes:
    if baseline_shapes[key] == candidate_shapes[key]:
        continue
    filename, name = key
    assert filename == "tests/test_shoot_screens.py"
    assert name in ALLOWED_SIGNATURES
    old = baseline_shapes[key]
    new = candidate_shapes[key]
    assert old["args"] == ["tmp_path", "monkeypatch"]
    assert new["args"] == ["preview_narrow_failure_walk"]
    for field in ("posonlyargs", "kwonlyargs", "vararg", "kwarg", "decorators"):
        assert old[field] == new[field], (key, field)
    changed.add(name)
assert changed == ALLOWED_SIGNATURES
```

An empty, missing, or fifth changed-signature set fails the gate.

- [ ] **Step 5: Instrument baseline timing work without replacing production**

Create `/tmp/stage_a_timing_plugin.py`:

```python
from __future__ import annotations

import json
import os
from pathlib import Path

_STATE = {"candidate_calls": 0, "commit_calls": 0, "oracle_calls": 0, "oracle_checks": 0}


def pytest_collection_finish(session):
    for module in {item.module for item in session.items}:
        if not str(getattr(module, "__file__", "")).endswith("tests/test_fleetsharing_timing.py"):
            continue
        real_candidate = module.candidate
        real_oracle = module.assert_candidate_matches_oracle
        real_commit = module.TimingContext._commit_diagnostic

        def candidate(*args, **kwargs):
            _STATE["candidate_calls"] += 1
            return real_candidate(*args, **kwargs)

        def oracle(prepared, exchanges):
            _STATE["oracle_calls"] += 1
            _STATE["oracle_checks"] += len(exchanges)
            return real_oracle(prepared, exchanges)

        def commit(self, prepared):
            _STATE["commit_calls"] += 1
            return real_commit(self, prepared)

        module.candidate = candidate
        module.assert_candidate_matches_oracle = oracle
        module.TimingContext._commit_diagnostic = commit


def pytest_sessionfinish(session, exitstatus):
    Path(os.environ["STAGE_A_TIMING_REPORT"]).write_text(
        json.dumps({**_STATE, "exitstatus": exitstatus}, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
```

Run the rolling ID with `-p stage_a_timing_plugin`; require `2,101` candidate calls, `2,101` commits, `2,101` oracle calls, and exactly `2,208,151` baseline membership checks.

- [ ] **Step 6: Instrument baseline screenshot walks**

Create `/tmp/stage_a_walk_plugin.py`:

```python
from __future__ import annotations

import json
import os
from pathlib import Path

_STATE = {"fixture_constructions": 0, "walks": []}
_WRAPPED = set()


def current_nodeid():
    return os.environ.get("PYTEST_CURRENT_TEST", "<collection>").rsplit(" (", 1)[0]


def pytest_collection_finish(session):
    for item in session.items:
        shoot = getattr(item.module, "shoot", None)
        if shoot is None or id(shoot) in _WRAPPED:
            continue
        real_walk = shoot.walk

        def counted_walk(*args, __real=real_walk, **kwargs):
            shots, skipped, eve_shown = __real(*args, **kwargs)
            _STATE["walks"].append(
                {
                    "nodeid": current_nodeid(),
                    "visited": [shot["key"] for shot in shots],
                    "skipped": [screen.key for screen in skipped],
                    "eve_shown": eve_shown,
                }
            )
            return shots, skipped, eve_shown

        shoot.walk = counted_walk
        _WRAPPED.add(id(shoot))


def pytest_fixture_setup(fixturedef, request):
    if fixturedef.argname == "preview_narrow_failure_walk":
        _STATE["fixture_constructions"] += 1


def pytest_sessionfinish(session, exitstatus):
    Path(os.environ["STAGE_A_WALK_REPORT"]).write_text(
        json.dumps(
            {
                **_STATE,
                "exitstatus": exitstatus,
                "walk_count": len(_STATE["walks"]),
                "visit_count": sum(len(row["visited"]) for row in _STATE["walks"]),
            },
            sort_keys=True,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
```

Run the normal 35-ID order. Require baseline exactly 35 real `shoot.walk()` calls and 515 visits: eight exact 61-key visits and 27 exact one-key visits. Independently import `scripts/shoot_screens.py` and require 61 unique ordered screens, 14 `at_floor`, and 13 whose `route == "fittings"`.

- [ ] **Step 7: Create the results ledger**

Create `docs/ci-broad-waste-reduction-stage-a-results.md` with these headings in order:

1. `Authority and exact source identities`
2. `PR #290 provenance and retained artifacts`
3. `Exact platform outcomes and normalized skips`
4. `Preview baseline and observer evidence`
5. `Timing baseline and bounded-oracle evidence`
6. `Screenshot baseline and focused-walk evidence`
7. `TDD RED/GREEN record`
8. `Mutation and fault qualification`
9. `Identity, order, and structure verification`
10. `Complete local endpoint`
11. `Reviews, scope, restoration, and leftovers`
12. `Publication stop and hosted evidence`
13. appendices containing exact targeted ID lists and skip arrays.

Do not prefill candidate/hosted outcomes. Baseline values must be literal verified outputs, not estimates or copied claims without artifact checks.

- [ ] **Step 8: Verify and commit Task 1**

```bash
git diff --check
git status --short
git add docs/ci-broad-waste-reduction-stage-a-results.md
git diff --cached --name-only
git commit -m "docs: freeze broad CI waste baseline"
```

Expected staged path: only the results ledger. All tests remain baseline green.

---

### Task 2: TDD the Preview Trigger Observer

**Files:**
- Modify: `tests/test_preview_runtime_review.py`
- Modify narrowly: `tests/test_preview_presentation.py`
- Modify narrowly: `tests/test_preview_geometry_publication.py`
- Modify: `docs/ci-broad-waste-reduction-stage-a-results.md`
- Verify unchanged: all production and every other Preview test

**Interfaces:**
- Consumes: `PreviewRuntime._condition`, `_snapshot()`, `snapshot()`, `_callback`, the existing fixture `Condition`/state list, and Api's installed callback.
- Produces: `wait_state(predicate, *, trigger=None)`, `_wait_for_runtime_state(runtime, predicate, states, trigger) -> None`, and `trigger_and_wait_state(rig, predicate, trigger) -> None`; trigger mode has one outer exceptional-exit boundary that preserves exception identity and performs owned-only callback cleanup under `runtime._condition`.

- [ ] **Step 1: Assemble the complete candidate in a disposable archive first**

Extract `463bccb0` into a fresh `/tmp/wingman-stage-a-candidate`; apply every permanent snippet in Tasks 2–3; Ruff-format only the five candidate test files; compile and run the 494-case relevant selection. Require `494 passed` before writing repository tests. Never copy caches, XML, scripts, or generated evidence into the worktree.

- [ ] **Step 2: Establish collectable RED on the exact four existing identities**

Capture original bytes/hash/binary diff/NUL status for the three Preview files. Add the helper imports and convert only the four calls, and add this temporary collectable stub in `test_preview_runtime_review.py`:

```python
def trigger_and_wait_state(rig, predicate, trigger) -> None:
    raise AssertionError("trigger wait not implemented")
```

Run the exact Preview-four nodes with `--junitxml=/tmp/stage-a-preview-red.xml`. Require all four IDs collect in their frozen order, each outcome is call-phase `failure`, and each traceback contains exactly `AssertionError: trigger wait not implemented`; reject `ImportError`, `NameError`, collection/setup error, skip, or timeout. In a `finally`, restore all three files and prove exact bytes/hash/binary diff/NUL status before continuing. Then apply the same imports/call conversions for GREEN and replace the stub with the real helper. RED is never committed.

- [ ] **Step 3: Replace only the fixture wait closure**

Change the fixture closure to:

```python
        def wait(predicate, *, trigger=None):
            _wait_for_runtime_state(
                runtime,
                predicate,
                (changed, states),
                trigger,
            )
```

Keep `r.states` as the original mutable fixture list and keep `eve_on()` byte-for-byte unchanged.

- [ ] **Step 4: Add the exact two-mode helper**

Add `from time import monotonic`, then insert before `parked()`:

```python
def _wait_for_runtime_state(runtime, predicate, states, trigger) -> None:
    changed, fixture_states = states
    if trigger is None:
        with changed:
            assert changed.wait_for(lambda: predicate(runtime.snapshot()), 5), (
                fixture_states
            )
        return

    completed = Condition()
    successful_states = []
    callback_errors = []
    observer_marker = "_wingman_trigger_wait_observer"

    with runtime._condition:
        current = runtime._snapshot()
        assert not predicate(current), (
            "trigger target was already satisfied",
            fixture_states,
            current,
        )
        delegate = runtime._callback
        assert delegate is not None, "trigger wait requires a current callback"
        assert not getattr(delegate, observer_marker, False), (
            "concurrent trigger waits are unsupported"
        )

        def observer(state):
            try:
                result = delegate(state)
            except Exception as error:
                with completed:
                    callback_errors.append(error)
                    completed.notify_all()
                raise
            with completed:
                successful_states.append(state)
                completed.notify_all()
            return result

        setattr(observer, observer_marker, True)
        runtime._callback = observer

    body_error = None
    body_tb = None
    try:
        trigger()
        deadline = monotonic() + 5
        observed = 0
        while True:
            with completed:
                completed.wait_for(
                    lambda: callback_errors or len(successful_states) > observed,
                    max(0, deadline - monotonic()),
                )
            with runtime._condition, completed:
                error = callback_errors[0] if callback_errors else None
                current = runtime._snapshot()
                ready = error is None and any(
                    predicate(state) and state == current for state in successful_states
                )
                timed_out = error is None and not ready and monotonic() >= deadline
                if error is not None or ready or timed_out:
                    if runtime._callback is observer:
                        runtime._callback = delegate
                    terminal = (error, ready)
                    diagnostics = (
                        fixture_states,
                        current,
                        tuple(successful_states),
                        tuple(callback_errors),
                    )
                else:
                    observed = len(successful_states)
                    terminal = None
            if terminal is None:
                continue
            error, ready = terminal
            if error is not None:
                raise error
            if ready:
                return
            raise AssertionError(
                ("preview runtime trigger did not complete", *diagnostics)
            )
    except BaseException as error:  # noqa: BLE001 -- cleanup covers every exit.
        body_error = error
        body_tb = error.__traceback__
    finally:
        try:
            with runtime._condition:
                if runtime._callback is observer:
                    runtime._callback = delegate
                assert runtime._callback is not observer, (
                    "preview trigger observer cleanup left wrapper installed"
                )
        except BaseException as cleanup_error:
            if body_error is None:
                raise
            raise body_error.with_traceback(body_tb) from cleanup_error
        if body_error is not None:
            raise body_error.with_traceback(body_tb)


def trigger_and_wait_state(rig, predicate, trigger) -> None:
    rig.wait_state(predicate, trigger=trigger)
```

This is intentionally private-field test coupling. Installation and every terminal error/success/timeout decision use direct assignment under `runtime._condition`; final error selection, current-snapshot comparison, ownership check, and owned disarm occur in the same critical section. A callback error appended to `callback_errors` before that section relinquishes observer ownership therefore wins over readiness. The fresh `completed` condition never acquires `runtime._condition`; finalization uses the one lock order `runtime._condition` → `completed`, avoiding inversion.

The outer `try/finally` begins immediately before `trigger()` and encloses the entire wait/finalization loop. Therefore trigger failures, `KeyboardInterrupt`, any other `BaseException`, a local `Condition.wait_for()` failure, predicate/snapshot failure, and terminal callback/timeout errors all reach the same owned-only cleanup. Cleanup reacquires `runtime._condition`, restores `delegate` only while `runtime._callback is observer`, and asserts that the marked observer is no longer current; a legitimate replacement is never overwritten. A terminal path that already disarmed makes this final cleanup a no-op. The helper never calls `set_state_callback()`, resets `_published`, calls `_wake()`, notifies the production condition, republishes state, or invokes either callback during restoration.

Exception precedence is exact: after successful cleanup, the original body exception object is re-raised with its captured traceback retained. If cleanup itself raises while another exception is active, that original object remains the raised/primary exception and the cleanup exception is attached as its explicit `__cause__`; neither is silently lost. If cleanup alone fails during a normal return, its exact exception propagates. A cleanup failure means restoration cannot be claimed and is a stopping failure. The cleanup-failure probe arranges a legitimate replacement before lock reacquisition fails, so it can still require that no marked observer is current. This intentionally differs from the disposable mutation runner: the runtime-test helper preserves the interrupted operation as required by the spec, while the mutation runner makes a restoration mismatch primary because invalid restored test evidence must stop the matrix.

- [ ] **Step 5: Convert exactly two presentation calls/imports**

Replace the `eve_on` import with ordered imports:

```python
from tests.test_preview_runtime_review import runtime_pump as runtime_pump
from tests.test_preview_runtime_review import trigger_and_wait_state
```

At each of the two named tests replace `eve_on(r)` with:

```python
    trigger_and_wait_state(
        r,
        lambda state: state.eve == "active",
        lambda: r.runtime.set_eve(True, 1),
    )
```

No other byte in `tests/test_preview_presentation.py` changes.

- [ ] **Step 6: Convert exactly two geometry transitions/imports**

Use the same ordered imports. Replace retained-drag `eve_on(r)` with the EVE snippet above. Replace only the companions `[True]` branch with:

```python
    if companions:
        trigger_and_wait_state(
            r,
            lambda state: state.companions == "active",
            lambda: r.runtime.set_companions(True, 1),
        )
```

The `[False]` row performs no trigger wait. No other geometry byte changes.

- [ ] **Step 7: Run GREEN and static structure checks**

Run the exact four IDs and require `4 passed`. AST-scan calls and require exactly four `trigger_and_wait_state()` call expressions: two presentation, one geometry EVE, one geometry companions. Require no fifth call, unchanged predicates, each dynamic call count exactly one, and exact `eve_on()` source/hash `685f6f...`. Expected old disconnected timeout waits are structurally zero; do not replace that statement with an elapsed threshold.

- [ ] **Step 8: Qualify legacy, waiter, terminal, and exceptional cleanup paths with temporary tests**

Materialize `/tmp/test_stage_a_preview_observer.py` with an in-memory runtime double exposing `_condition`, `_callback`, `_snapshot()`, and `snapshot()`. It must collect these exact 18 IDs:

```text
test_stage_a_preview_observer.py::test_legacy_snapshot_can_return_while_callback_is_blocked[direct]
test_stage_a_preview_observer.py::test_legacy_snapshot_can_return_while_callback_is_blocked[composed]
test_stage_a_preview_observer.py::test_trigger_wait_arms_before_trigger_and_waits_for_exact_delegate_result
test_stage_a_preview_observer.py::test_wait_condition_cannot_complete_before_blocked_delegate
test_stage_a_preview_observer.py::test_terminal_finalization_prioritizes_error_before_owned_disarm
test_stage_a_preview_observer.py::test_wait_baseexception_restores_owned_observer
test_stage_a_preview_observer.py::test_wait_baseexception_preserves_legitimate_replacement
test_stage_a_preview_observer.py::test_cleanup_failure_is_chained_without_masking_wait_baseexception
test_stage_a_preview_observer.py::test_delegate_is_called_once_with_exact_state_and_return
test_stage_a_preview_observer.py::test_matching_completion_must_equal_the_current_snapshot
test_stage_a_preview_observer.py::test_matching_callback_error_is_exact_and_never_successful[none]
test_stage_a_preview_observer.py::test_matching_callback_error_is_exact_and_never_successful[partial]
test_stage_a_preview_observer.py::test_nonmatching_error_precedes_later_matching_success
test_stage_a_preview_observer.py::test_replacement_during_delegate_is_not_overwritten
test_stage_a_preview_observer.py::test_sequential_waits_restore_exact_callback_without_accumulation
test_stage_a_preview_observer.py::test_concurrent_wait_is_rejected_before_its_trigger_runs
test_stage_a_preview_observer.py::test_already_satisfied_target_fails_before_install_or_trigger
test_stage_a_preview_observer.py::test_trigger_error_is_exact_and_restores_owned_observer
```

Use real `Condition`, `Event`, `Thread`, and barriers. The runtime double's production-style catch stores the exact exception object. For the waiter and terminal races, monkeypatch only the helper module's fresh `Condition` constructor to return this temporary instrumented condition; the runtime double keeps a real independent condition:

```python
class WaitInterrupted(BaseException):
    pass


class InterruptingWaitCondition:
    """Compose a real condition but interrupt the wait with one exact object."""

    def __init__(self, sentinel):
        self._condition = ThreadCondition()
        self._sentinel = sentinel
        self.calls = 0

    def __enter__(self):
        self._condition.acquire()
        return self

    def __exit__(self, *exc):
        self._condition.release()

    def notify_all(self):
        self._condition.notify_all()

    def wait_for(self, predicate, timeout=None):
        self.calls += 1
        raise self._sentinel


class FailingEntryCondition:
    """Compose a real condition and raise on one selected acquisition."""

    def __init__(self, sentinel, fail_on):
        self._condition = ThreadCondition()
        self._sentinel = sentinel
        self._fail_on = fail_on
        self.entries = 0

    def __enter__(self):
        self.entries += 1
        if self.entries == self._fail_on:
            raise self._sentinel
        self._condition.acquire()
        return self

    def __exit__(self, *exc):
        self._condition.release()


class WaitProbeCondition:
    def __init__(self):
        self._condition = ThreadCondition()
        self.evaluated = Event()
        self.matched = Event()
        self.resume = Event()
        self.returned = Event()
        self._first = True

    def __enter__(self):
        self._condition.acquire()
        return self

    def __exit__(self, *exc):
        self._condition.release()

    def notify_all(self):
        self._condition.notify_all()

    def wait_for(self, predicate, timeout=None):
        if self._first:
            self._first = False
            result = predicate()
            self.evaluated.set()
            if result:
                self.matched.set()
            self._condition.release()
            try:
                assert self.resume.wait(5), "wait probe was not released"
            finally:
                self._condition.acquire()
            if result:
                self.returned.set()
                return True
        result = self._condition.wait_for(predicate, timeout)
        if result:
            self.returned.set()
        return result
```

The premature-completion witness must prove, in order: trigger returned (`trigger_complete` set), delegate is still barrier-held, the waiter evaluated its local wait predicate, and `probe.returned` plus the future remain unset. It then opens `probe.resume`, waits one second for the explicit `returned` event, and fails only with `"wait condition returned before delegate completion"` if the notify-before-delegate mutant escapes; only afterward does it release the delegate.

The terminal-race witness first delivers a successful matching state, pauses the waiter at `probe.matched` after readiness wake but before atomic finalization, invokes the already-captured observer with a nonmatching state whose delegate raises `RuntimeError("terminal nonmatching callback error")`, confirms production catch identity, and then releases the waiter. The waiter must raise that exact object, and owned disarm must restore the delegate. This deterministically proves an armed error recorded before ownership relinquishment wins over the earlier readiness wake.

Add these three deterministic exceptional-exit probes using `InterruptingWaitCondition` and `FailingEntryCondition`. They monkeypatch only the helper's local `Condition`; the runtime's own `_condition` remains a real independent condition:

```python
def test_wait_baseexception_restores_owned_observer(monkeypatch):
    sentinel = WaitInterrupted("condition wait interrupted while observer owned")
    completed = InterruptingWaitCondition(sentinel)
    monkeypatch.setattr(review, "Condition", lambda: completed)

    def delegate(state):
        return state

    runtime = RuntimeDouble(delegate)
    installed = []

    def trigger():
        installed.append(runtime._callback)
        assert getattr(installed[0], "_wingman_trigger_wait_observer", False)

    with pytest.raises(WaitInterrupted) as caught:
        wait(runtime, lambda state: state.active, trigger)
    assert caught.value is sentinel
    assert completed.calls == 1
    assert runtime._callback is delegate, (
        "owned exceptional cleanup did not restore delegate"
    )
    assert runtime._callback is not installed[0]
    assert not getattr(runtime._callback, "_wingman_trigger_wait_observer", False)


def test_wait_baseexception_preserves_legitimate_replacement(monkeypatch):
    sentinel = WaitInterrupted("condition wait interrupted after replacement")
    completed = InterruptingWaitCondition(sentinel)
    monkeypatch.setattr(review, "Condition", lambda: completed)

    def delegate(state):
        return state

    def replacement(state):
        return state

    runtime = RuntimeDouble(delegate)
    installed = []

    def trigger():
        with runtime._condition:
            installed.append(runtime._callback)
            assert getattr(installed[0], "_wingman_trigger_wait_observer", False)
            runtime._callback = replacement

    with pytest.raises(WaitInterrupted) as caught:
        wait(runtime, lambda state: state.active, trigger)
    assert caught.value is sentinel
    assert completed.calls == 1
    assert runtime._callback is replacement, (
        "exceptional cleanup overwrote legitimate replacement"
    )
    assert runtime._callback is not installed[0]
    assert not getattr(runtime._callback, "_wingman_trigger_wait_observer", False)


def test_cleanup_failure_is_chained_without_masking_wait_baseexception(monkeypatch):
    body_sentinel = WaitInterrupted("condition wait interrupted before cleanup")
    cleanup_sentinel = RuntimeError("runtime condition failed during cleanup")
    completed = InterruptingWaitCondition(body_sentinel)
    monkeypatch.setattr(review, "Condition", lambda: completed)

    def delegate(state):
        return state

    def replacement(state):
        return state

    runtime = RuntimeDouble(delegate)
    runtime._condition = FailingEntryCondition(cleanup_sentinel, fail_on=3)
    installed = []

    def trigger():
        with runtime._condition:
            installed.append(runtime._callback)
            assert getattr(installed[0], "_wingman_trigger_wait_observer", False)
            runtime._callback = replacement

    with pytest.raises(WaitInterrupted) as caught:
        wait(runtime, lambda state: state.active, trigger)
    assert caught.value is body_sentinel
    assert caught.value.__cause__ is cleanup_sentinel
    assert runtime._condition.entries == 3
    assert runtime._callback is replacement
    assert runtime._callback is not installed[0]
    assert not getattr(runtime._callback, "_wingman_trigger_wait_observer", False)
```

The first proves a unique non-`Exception` interruption from `Condition.wait_for()` escapes as the exact object and owned cleanup restores the original delegate. The second installs a legitimate replacement before the same interruption and proves `finally` preserves it. The third makes the cleanup lock acquisition itself fail after a legitimate replacement: the exact wait interruption remains primary, the exact cleanup failure is its `__cause__`, and the replacement remains current. All three assert that no marked observer remains current. Their JUnit outcomes must be `passed`; an uncaught `WaitInterrupted` is an `error`, not acceptable evidence. Do not weaken these boundaries to `Exception`, generic failure text, or final callback inequality alone.

The two legacy rows separately prove: direct fixture `publish` can remain blocked before acquiring its condition after snapshot truth, and a composed Api-first/publish-second callback can remain blocked before its publish tail. Both no-trigger waits may return while `callback_complete` is false, `fixture_states` is empty, and composed Api effects are absent; neither row is callback-completion evidence.

Collect the external file through the exact-ID plugin, run all 18 with JUnit, parse through the explicit one-component classname map, and require `18 passed`. Also prove exact state/delegate result/error identity, matching no/partial reconciliation failure, nonmatching-first error precedence, current-state equality, replacement preservation, sequential depth one, concurrent rejection before trigger, stale-target rejection, exact trigger-error cleanup, exact waiter-side `BaseException` identity, owned exceptional cleanup, replacement-safe exceptional cleanup, exact cleanup-failure `__cause__`, and no current marked wrapper.

- [ ] **Step 9: Run eight observer mutants with exact per-ID JUnit ownership**

Apply each mutation separately with the `finally`-safe wrapper. Every row runs exactly one selected external node, requires call-phase `failure`, preserves traceback, matches only its unique regex below, and forbids `Timeout`, `timed out`, `wait probe was not released`, fixture setup, collection error, setup/teardown error, or another observer assertion:

| Mutant | Exact match-once change | Exact selected ID suffix | Required unique regex |
|---|---|---|---|
| missing delegation | `result = delegate(state)` → `result = None` | `test_delegate_is_called_once_with_exact_state_and_return` | `captured delegate did not receive the exact state once` |
| premature notify | move successful append/notify before `delegate(state)` | `test_wait_condition_cannot_complete_before_blocked_delegate` | `wait condition returned before delegate completion` |
| callback error counted as success | append to `successful_states` instead of `callback_errors` in `except` | `test_matching_callback_error_is_exact_and_never_successful[none]` | `DID NOT RAISE ValueError` |
| first error ignored | `error = callback_errors[0] if callback_errors else None` → `error = None` | `test_nonmatching_error_precedes_later_matching_success` | `DID NOT RAISE RuntimeError` |
| terminal-race error ignored | the same isolated edit in a separately restored run | `test_terminal_finalization_prioritizes_error_before_owned_disarm` | `DID NOT RAISE RuntimeError` |
| unconditional restore | terminal owned check → `if True:` | `test_replacement_during_delegate_is_not_overwritten` | `replacement callback was overwritten` |
| wrapper accumulation | delete the marked-delegate assertion | `test_concurrent_wait_is_rejected_before_its_trigger_runs` | `concurrent trigger ran` |
| exceptional cleanup deleted | remove only the owned `runtime._callback = delegate` branch inside the outer `finally` | `test_wait_baseexception_restores_owned_observer` | `owned exceptional cleanup did not restore delegate` |

After every mutation, rerun the unmutated terminal race, premature-completion, all three wait-interruption/cleanup-failure cases, matching `[partial]`, stale-target, trigger-error, and sequential cases. Aggregate ordinary intended failures; restoration mismatch is fatal and stops the matrix.

- [ ] **Step 10: Run complete Preview consumer verification**

```bash
uv run --no-sync python -m pytest \
  tests/test_preview_runtime_review.py \
  tests/test_preview_runtime_boundaries.py \
  tests/test_preview_layout_batch.py \
  tests/test_preview_layout_admission.py \
  tests/test_preview_polish_fixes.py \
  tests/test_preview_presentation.py \
  tests/test_preview_geometry_publication.py \
  tests/test_preview_wiring.py \
  -q -rs --durations=30 --junitxml=/tmp/stage-a-preview-388.xml
```

Expected: exact 388 IDs/order/hash and all passing. Verify production protected hashes and every other `runtime_pump` consumer unchanged.

- [ ] **Step 11: Record evidence and commit Task 2**

```bash
uv run --extra dev ruff check \
  tests/test_preview_runtime_review.py \
  tests/test_preview_presentation.py \
  tests/test_preview_geometry_publication.py
uv run --extra dev ruff format --check \
  tests/test_preview_runtime_review.py \
  tests/test_preview_presentation.py \
  tests/test_preview_geometry_publication.py
git diff --check
git add \
  tests/test_preview_runtime_review.py \
  tests/test_preview_presentation.py \
  tests/test_preview_geometry_publication.py \
  docs/ci-broad-waste-reduction-stage-a-results.md
git diff --cached --name-only
git commit -m "test: observe Preview trigger readiness"
```

Expected staged paths: exactly those four. Results record literal sentinel RED/GREEN, exact four calls, 18 probe outcomes, 8 exact-ID mutant failures, external-JUnit parser self-test, exact restoration, 388 green, and no timing claim.

---

### Task 3: TDD the Bounded Timing Oracle and Focus Screenshot Walks

**Files:**
- Modify: `tests/test_fleetsharing_timing.py`
- Modify: `tests/test_shoot_screens.py`
- Modify: `docs/ci-broad-waste-reduction-stage-a-results.md`
- Verify unchanged: `scripts/shoot_screens.py`, `tests/test_new_screenshots.py`, `tests/test_current_screenshots.py`, all fixtures and production

**Interfaces:**
- Consumes: unchanged `diagnostic_oracle()`, `assert_candidate_matches_oracle()`, `shoot.SCREENS`, and `shoot.walk()`.
- Produces: independent 95-second expected slice, `_walk_screens(*keys)`, frozen 61-key contract, `PreviewFailureReceipt`, and module fixture `preview_narrow_failure_walk`.

- [ ] **Step 1: Establish timing RED structurally**

With the baseline timing plugin, add a temporary assertion `oracle_checks == 197136` before changing the rolling body. Run the rolling ID. Require RED because actual baseline is exactly `2,208,151`; remove the temporary assertion. This RED is evidence only and is not committed.

- [ ] **Step 2: Bound only the rolling expected input**

Replace only the oracle call inside the rolling loop:

```python
        # The protocol retains request starts no older than 95 seconds. This
        # trace has fixed one-second request-start cadence.
        first_retained = max(0, second - 95)
        expected = exchanges[first_retained:]
        assert_candidate_matches_oracle(prepared, expected)
```

Do not read candidate state, `_DIAGNOSTIC_WINDOW_MS`, `_DIAGNOSTIC_CAPACITY`, or a production cutoff to choose `expected`. Leave construction, `before`, candidate, detached assertion, commit, `<= 96`, final server, and inconsistency assertions unchanged.

- [ ] **Step 3: Run timing GREEN and exact instrumentation**

Run the rolling ID with the plugin. Require exactly `2,101` candidates, `2,101` commits, `2,101` oracle calls, and `197,136` membership checks. Then run all 41 timing IDs. Require exact order/hash and all passing.

- [ ] **Step 4: Run nine timing mutations**

Use exact match-once production mutations in `wingman/fleetsharing/timing.py`, restore after each, and require these witnesses:

| Defect | Exact edit | Intended retained witness |
|---|---|---|
| exclusive boundary | pruning `<=` → `<` | binary ratio `[95.0-2]` exact vector |
| receipt not request start | `r - e.started_at` → `r - e.received_at` | request-start test exact vector |
| no pruning | pruning condition → `if True` | rolling first expired-prefix vector |
| 94-second window | subtract `1000` from literal aggregate | binary ratio `[95.0-2]` |
| 96-second window | add `1000` | binary ratio `[95.00000000000001-1]` |
| wrong 95/96 capacity | `_DIAGNOSTIC_CAPACITY = 95` | rolling `prepared is not None` at the edge |
| stalled server time | install prior `last_server_time_ms` | rolling exact final `2202100` |
| legal recurrence latches | return `_ClockContradiction(state)` at server `1101000` | rolling candidate/commit recurrence |
| candidate/commit confusion | install `candidate.base` instead of `candidate.state` | rolling exact vector/detached/final state |

Require all nine intended REDs and exact restoration. A defensive overflow-only failure is not accepted when an earlier exact vector should own the defect.

- [ ] **Step 5: Freeze original production `Screen` objects at import**

Add imports:

```python
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
```

Immediately after `shoot = _load()` add `_PRODUCTION_SCREENS = tuple(shoot.SCREENS)`, the exact 61-key tuple from the spec, `_SCREEN_BY_KEY`, import-time uniqueness/order assertions, and:

```python
def _walk_screens(*keys):
    assert len(keys) == len(set(keys)), keys
    selected = tuple(_SCREEN_BY_KEY[key] for key in keys)
    assert tuple(screen.key for screen in selected) == keys
    return selected
```

`_walk_screens()` returns the original objects and preserves caller order. It creates no second `Screen` inventory and fails missing/duplicate/reordered selections immediately.

- [ ] **Step 6: Keep one complete traversal and focus three independent walks**

- Setup-failure ID monkeypatches exactly `_walk_screens("settings-previews-groups", "settings-previews-narrow")` and asserts exact two visited keys plus both errors.
- Full metrics ID does not monkeypatch `shoot.SCREENS`; add these separate assertions before existing floor assertions:

```python
assert tuple(shot["key"] for shot in shots) == _EXPECTED_FULL_SCREEN_KEYS
assert all(shot["error"] is None for shot in shots), shots
```

  In `_TrackedCDP.screenshot()`, append `"capture_success"` only after the failure branch, immediately before returning PNG bytes. Keep exact floor set/clear counts, then consume the complete operation trace as a state machine:

```python
floor_active = False
floor_captured = False
for operation in cdp._ops:
    if operation == "set:840x625":
        assert not floor_active, (
            "floor metrics set nested before prior clear",
            cdp._ops,
        )
        floor_active = True
        floor_captured = False
    elif operation == "capture_success" and floor_active:
        assert not floor_captured, (
            "floor metrics interval captured more than once",
            cdp._ops,
        )
        floor_captured = True
    elif operation == "clear":
        assert floor_active, (
            "floor metrics clear without active set",
            cdp._ops,
        )
        assert floor_captured, (
            "floor metrics clear before successful capture",
            cdp._ops,
        )
        floor_active = False
        floor_captured = False
assert not floor_active, (
    "floor metrics interval remained active at traversal end",
    cdp._ops,
)
```

  Give the set/clear count assertions unique messages `"floor set count mismatch"` and `"floor clear count mismatch"`. This makes the retained full traversal—not the Preview-focused row—own omission and exact ordering for every non-Preview floor branch as well as all 14 floor visits. It rejects a nested set, second floor or non-floor capture before clear, stray clear, clear before capture, and an active interval at traversal end.
- Successful Preview order ID monkeypatches exactly `_walk_screens("settings-previews-narrow")` and retains set → setup → screenshot → clear.
- Fittings ID derives keys only from `_PRODUCTION_SCREENS if screen.route == "fittings"`, asserts the exact 13-key tuple, monkeypatches `_walk_screens(*fitting_keys)`, asserts exact visits and 13 injections, and for every stage after the first requires `stage[0] == shoot._fittings_reset_script()` before the existing reset/action assertion.

- [ ] **Step 7: Add one immutable module-scoped failure receipt**

After `_FailOnceCDP`, add:

```python
@dataclass(frozen=True)
class PreviewFailureReceipt:
    shots: tuple[Mapping[str, object], ...]
    operations: tuple[str, ...]
    override_active: bool


@pytest.fixture(scope="module")
def preview_narrow_failure_walk(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            shoot,
            "SCREENS",
            _walk_screens("settings-previews-narrow"),
        )
        patch.setattr(shoot.time, "sleep", lambda _: None)
        cdp = _FailOnceCDP(fail_narrow_screenshot=True)
        shots, skipped, eve_shown = shoot.walk(
            cdp,
            tmp_path_factory.mktemp("preview-narrow-failure"),
            settle_ms=0,
        )
        assert eve_shown is True
        assert not skipped
        assert tuple(shot["key"] for shot in shots) == (
            "settings-previews-narrow",
        )
        detached_shots = tuple(MappingProxyType(dict(shot)) for shot in shots)
        operations = tuple(cdp._ops)
        override_active = cdp._override_active
    return PreviewFailureReceipt(detached_shots, operations, override_active)
```

Convert the four failure-order IDs to consume this fixture. Keep each assertion owner: failed shot/error, clear and inactive override, setup inside override, exact tuple `("set:840x625", "eval:setup", "screenshot_attempt", "clear")`, and attempt between set/clear. Tuple slices compare with tuples. The fixture returns only after the monkeypatch context exits and retains no CDP/path/mutable operations/live patch.

- [ ] **Step 8: Run exact eight screenshot IDs and each receipt consumer directly**

Require all eight existing IDs pass, exact selectors are `2/61/1/shared-1/13`, the full traversal has 14 floor intervals that each contain exactly one successful capture and close before any later capture or set, all errors are `None`, Preview success/failure order is exact, and all 13 Fittings screens/injections are exact. No ID or parameter changes.

Then run this unmutated four-consumer selection as its own command and require `4 passed` with one module receipt construction:

```text
tests/test_shoot_screens.py::test_walk_clears_device_metrics_even_when_narrow_screenshot_fails
tests/test_shoot_screens.py::test_walk_narrow_setup_runs_inside_device_metrics_override_on_failure
tests/test_shoot_screens.py::test_walk_failure_path_records_set_eval_attempt_clear_in_order
tests/test_shoot_screens.py::test_walk_failure_path_records_attempt_before_clear_not_only_clear
```

Run each of those four node IDs again in a separate pytest invocation and require `1 passed` each. Direct-selection executions may construct one receipt per process; do not combine those four construction counts into the structural singleton claim.

- [ ] **Step 9: Run lifetime-safe structural orders**

Use the Task 1 walk plugin and exact 35-ID blocks. Execute separate pytest processes for:

1. collected order;
2. reverse only inside the contiguous 15-ID `test_shoot_screens.py` block;
3. `random.Random(20260926).shuffle()` only inside that block;
4. one round-robin mixed/interleaved cross-module order.

For each of the first three require exact identity hash shown above, 35 passing unique IDs, one receipt construction, 32 real walks, and 105 visits with lengths `[1] * 29 + [2, 13, 61]`. Require one exact full list, one exact Fittings list, and one exact two-Preview list. For mixed order require only the exact 35 identity set and all passing outcomes; record observed counts only as diagnostics. Never claim singleton/32/105 across module teardown/re-entry.

- [ ] **Step 10: Run the 14 original screenshot mutants/faults plus the deferred-clear polish mutation**

Apply and restore each independently. Require per-ID JUnit intended failures:

| Defect | Witness |
|---|---|
| omit first `screens_for_gate(True)` result | full exact 61 keys |
| reorder first two results | full exact 61 keys |
| first ordinary `_TrackedCDP` capture (`uploader`) raises | exact keys still hold; separate all-errors assertion fails |
| omit every non-early floor override | Preview success-order cannot find `set:840x625` |
| omit only non-Preview `fittings-narrow` override | retained full traversal fails `floor set count mismatch` |
| defer only the 12th floor set (`fittings-narrow`) until after `capture_success` but before clear | retained full traversal keeps set/clear parity yet fails `floor metrics clear before successful capture` |
| defer every clear until after `walk()` returns, preserving all counts and nth set/clear ordering | old pairing assertion passes before the edit; the exact state machine fails `floor metrics interval captured more than once` after the edit |
| skip group setup | exact two-shot setup-failure ID fails group error assertion |
| skip narrow setup | same ID fails narrow error assertion |
| verifier after screenshot | focused Preview postcondition ID records capture and fails `captures == []` |
| replace screenshot call with bytes (no attempt) | shared attempt-order consumer fails |
| omit final clear | shared clear/inactive consumer fails |
| omit cleanup evaluation | selected existing new/current cleanup IDs each fail independently |
| move Fittings injection after reset/preparation | Fittings ID fails `stage[0]` reset ordering |
| derive Fittings selector while omitting `fittings-unfiled` | exact 13-key assertion fails |

The ordinary uploader probe must explicitly report that ordered keys passed and failure occurred at `all(shot["error"] is None for shot in shots)`. Every row requires exact selected JUnit IDs, call-phase failure, the named unique assertion/traceback, and no setup/collection/timeout masking. Restore all source/test-double bytes before the next row.

- [ ] **Step 11: Run relevant suites and commit Task 3**

Run all 41 timing tests; exact eight and 35 screenshot selections; complete `test_shoot_screens.py`, `test_new_screenshots.py`, and `test_current_screenshots.py`; executable screenshot DOM/worker tests; and the 494-case relevant selection. Then:

```bash
uv run --extra dev ruff check tests/test_fleetsharing_timing.py tests/test_shoot_screens.py
uv run --extra dev ruff format --check tests/test_fleetsharing_timing.py tests/test_shoot_screens.py
git diff --check
git diff --exit-code -- scripts/shoot_screens.py tests/test_new_screenshots.py tests/test_current_screenshots.py
git add \
  tests/test_fleetsharing_timing.py \
  tests/test_shoot_screens.py \
  docs/ci-broad-waste-reduction-stage-a-results.md
git diff --cached --name-only
git commit -m "test: focus broad CI waste checks"
```

Expected staged paths: exactly those three. Results record RED/GREEN, `2,208,151 -> 197,136`, `35/515 -> 32/105`, all mutation witnesses, and no speedup projection.

---

### Task 4: Complete the Local Endpoint

**Files:**
- Modify: `docs/ci-broad-waste-reduction-stage-a-results.md`
- Verify: exact eight-path allowed scope and every protected path/hash

**Interfaces:**
- Consumes: Tasks 1–3 green implementation and all local evidence.
- Produces: complete local acceptance with exact 16,609 identities, `16,595 + 14`, mandatory tool gates, final mutation rerun, scope/protected hashes, and no leftovers.

- [ ] **Step 1: Rebuild mandatory prerequisites**

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-broad-waste-stage-a
uv sync --locked --extra dev
node --version
cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os, pathlib, shutil; from wingman.evesettings import codec; name = 'wingman-settings-codec' + ('.exe' if os.name == 'nt' else ''); source = pathlib.Path('packaging/settings-codec/target/release') / name; target = pathlib.Path('packaging/bin') / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); assert codec.codec_available(), 'Native integration tests require the built codec'"
```

- [ ] **Step 2: Re-run exact focused/order/consumer selections**

Require:

- Preview four and Preview 388 exact identities/order;
- all 18 temporary observer IDs pass with exact waiter-interruption identity, owned restoration, legitimate-replacement preservation, cleanup-failure cause chaining, and no current marked wrapper;
- rolling one and timing 41 exact identities/order;
- screenshot eight, 15, 35, and three structural orders exact;
- mixed 35 outcome-only green;
- the relevant selection exact 494;
- all target IDs invoke the intended helper/walk exactly as recorded, with no fifth trigger call and unchanged `eve_on()`.

Do not retry an order to green. A failed first run is evidence and must be investigated/recorded.

- [ ] **Step 3: Run relevant Api/protocol/isolation/lifecycle suites**

```bash
uv run --no-sync python -m pytest \
  tests/test_preview_runtime_review.py \
  tests/test_preview_runtime_boundaries.py \
  tests/test_preview_layout_batch.py \
  tests/test_preview_layout_admission.py \
  tests/test_preview_polish_fixes.py \
  tests/test_preview_presentation.py \
  tests/test_preview_geometry_publication.py \
  tests/test_preview_wiring.py \
  tests/test_api.py \
  tests/test_fleet_presentation_worker.py \
  tests/test_fleetsharing_timing.py \
  tests/test_fleetsharing_timing_publisher.py \
  tests/test_fleetsharing_timing_receiver.py \
  tests/test_fleetsharing_protocol.py \
  tests/test_fleetsharing_protocol_bindings.py \
  tests/test_fleetsharing_protocol_review.py \
  tests/test_fleetsharing_protocol_vectors.py \
  tests/test_node_scenario_worker.py \
  tests/test_shoot_screens.py \
  tests/test_new_screenshots.py \
  tests/test_current_screenshots.py \
  -q -rs --durations=50 --junitxml=/tmp/stage-a-relevant.xml
```

Record the exact outcome and any intentional platform skips; do not substitute a smaller smoke command.

- [ ] **Step 4: Run the complete suite**

```bash
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/stage-a-full.xml
uv run --no-sync python scripts/summarize_pytest_junit.py \
  /tmp/stage-a-full.xml /tmp/stage-a-full.json
```

Require exact `16,595 passed + 14 skipped = 16,609`; ordered ID equality/hash; exact normalized 14-skip array; zero failures/errors; and no Node/codec/unexpected native skip. Compare AST signatures/decorators/markers and per-file targeted identity order to Task 1.

- [ ] **Step 5: Run independent executable/tool gates**

```bash
node scripts/js_smoke.js
node tests/fixtures/screenshot_dom.test.cjs
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --no-sync python -m pytest tests/test_documentation.py -q
git diff --check 463bccb0..HEAD
```

The Python relevant-suite command above executes the existing screenshot worker scenarios; the direct Node DOM command independently exercises the fixture contract.

- [ ] **Step 6: Re-run every mutation/fault probe from the final tree**

Compile and Ruff-check all temporary scripts, then run all 8 observer, 9 timing, the 14 original screenshot mutants, and the deferred-clear polish mutant plus the unmutated 18 observer cases, literal four-ID RED, external-JUnit parser self-test, signature exception gate, restoration-failure simulation, and structural plugins. Require exact JUnit ownership, no masking/timeouts, and restoration exact bytes/hash/binary diff/NUL status after every row.

- [ ] **Step 7: Audit exact versioned scope and protected hashes**

```python
import hashlib
import subprocess
from pathlib import Path

base = "463bccb07077325e64b6ad7f7ce4e9c100d2fcd6"
allowed = {
    "docs/superpowers/specs/2026-09-26-ci-broad-waste-reduction-stage-a-design.md",
    "docs/superpowers/plans/2026-09-26-ci-broad-waste-reduction-stage-a.md",
    "docs/ci-broad-waste-reduction-stage-a-results.md",
    "tests/test_preview_runtime_review.py",
    "tests/test_preview_presentation.py",
    "tests/test_preview_geometry_publication.py",
    "tests/test_fleetsharing_timing.py",
    "tests/test_shoot_screens.py",
}
actual = set(
    subprocess.check_output(
        ["git", "diff", "--name-only", f"{base}..HEAD", "--", "."], text=True
    ).splitlines()
)
assert actual == allowed, sorted(actual ^ allowed)
protected = {
    "wingman/preview/runtime.py": "adde9c49b469fbffe7816c746da7078fbfcc88aada9412ad318193c3072101c0",
    "wingman/ui/api.py": "730298e68701348ce175d4db3fd75ac95c343b939d07052e0ea3d772a17615ce",
    "wingman/ui/fleetpresentation.py": "db714251d8744ecdb0862414126baf2aa887578af4f7c6919520e32e00246613",
    "wingman/fleetsharing/timing.py": "0b09ec89d47b803089015a6e21f80604219ec1b619909ca400e5e7e7d9520901",
    "scripts/shoot_screens.py": "05e03a76374d16719568eb92b461ef1b50a7e5ff35ef2cd3944b97aa3d4453b4",
    "tests/test_new_screenshots.py": "ffb2024c3931ab599c3e33cb9a1bbc4188224392fc1caadf58e989c58b29e157",
    "tests/test_current_screenshots.py": "1a6dabb9d2e6f8360268eab5045334d25c4ad09048ca99bfc166d80edf6bb021",
    ".github/workflows/ci.yml": "9524b760b9f74c09b39c7d096cf1e1494b16e6607e8a5c7422d97e9ee4811222",
    "pyproject.toml": "33620c99049ad82b1366b2c63cf9957ebb9ea928e08445b9ea8fefd28c789412",
    "uv.lock": "ebf5e1a5e892dd6488385d117c64a14dd0b0575ef9dbc4565b07a3012f9ad499",
}
for name, expected in protected.items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
```

Also require `git diff --exit-code 463bccb0..HEAD -- wingman scripts .github packaging pyproject.toml uv.lock tests/fixtures` and exact presentation/geometry narrow diffs.

- [ ] **Step 8: Scan for unfinished markers and leftovers**

Search changed paths for unfinished-marker comments, debug prints, temporary counters, mutation markers, local `/tmp` paths accidentally embedded in executable tests, zero budgets, disabled assertions, mutable receipt state, and Stage B/C implementation. Verify no XML/JSON/evidence archive is tracked or staged.

- [ ] **Step 9: Finish and commit local results**

Results must explicitly confirm every item in the spec's Required implementation self-review and include this conclusion:

```text
LOCAL CONCLUSION: Stage A preserves the exact ordered 16,609 identities and local outcomes while removing the approved same-identity deterministic work. Structural callback completion, 2,101 transitions/197,136 oracle checks, and 32 walks/105 visits are acceptance evidence. All elapsed values are observations only; no speedup, lower bound, p95, job, or critical-path claim is made.
```

Commit only results:

```bash
git add docs/ci-broad-waste-reduction-stage-a-results.md
git diff --cached --name-only
git commit -m "docs: record Stage A local verification"
```

---

### Task 5: Polish, Review, Freeze the Executable Head, and Stop Before Publication

**Files:**
- Modify only within the exact eight-path tranche if polish/review requires it
- Hosted reads/evidence only after publication authorization and release of the current parent-review hold

**Interfaces:**
- Consumes: fully green Task 4 tree and complete results.
- Produces: polished reviewed executable commit, frozen SHA, clean tree, change explanation, explicit local hold, and—after parent final review—logs-primary hosted contract evidence.

- [x] **Step 1: Run `polish-core --fix` and inspect every edit**

Review `463bccb0..HEAD`. Accept only high-confidence edits within the exact eight paths. Reject any production, helper, fixture, workflow, dependency, configuration, marker, selector, shard, timeout, packaging, or Stage B/C edit. Inspect polish changes rather than trusting the tool.

- [x] **Step 2: Run fresh verification after polish**

At minimum rerun Preview four/388, timing one/41 with exact counts, screenshot eight/35 plus three structural orders and mixed outcomes, the 494-case relevant selection, all mutation probes if executable tests changed, Ruff on five test files, documentation tests, exact scope/protected hashes, and `git diff --check`. If polish changes behavior-bearing test code, rerun the complete suite and all tool gates.

- [x] **Step 3: Perform final self-review and one independent review**

First run the complete checklist below yourself. Then, only if the implementation authorization permits subagents, call the configured `subagent` tool once with `subagent_type="review"`, `run_in_background=false`, a 3–5 word description, and a self-contained read-only prompt naming the approved spec, exact `463bccb0..HEAD` diff, results ledger, local JUnit/JSON, mutation reports, and this checklist. Do not let the reviewer edit files. If a review subagent/tool is unavailable or not authorized, stop before freezing/publishing and request explicit maintainer review of the same artifacts; do not substitute self-certification or silently skip the gate.

Execution used the already completed independent review: it found the floor-interval
gap, the correction landed in `83bd018b`, and re-review approved it. The current
instruction forbids new subagents, so this final evidence pass dispatched none.

The review must check atomic arm, false precondition, current callback capture, delegate-first completion, atomic terminal error/success decision plus owned disarm, terminal-race precedence, exact return/error identity, outer `try/finally` coverage across trigger and the complete wait loop, exact waiter-side `BaseException` preservation, owned exceptional cleanup, replacement-safe cleanup, visible cleanup-failure chaining, no current marked wrapper, current-state equality, replacement/no accumulation, five-second bound, exactly four calls, unchanged `eve_on()`, 2,101/197,136 timing structure, one 61/14 traversal, its exact inactive → set → one capture → clear → inactive state machine, non-Preview floor omission/reversal and deferred-clear qualification, exact 13 Fittings, immutable receipt/direct consumers, 32/105 safe-order structure, mixed-order claim discipline, exact identity/signature exceptions/skips/eight-path scope, restoration, and no unfinished markers.

- [x] **Step 4: Run `change-explainer` and update reviewer-facing results**

Record what changed, how each seam works, why private test coupling is intentional, edge/failure behavior, mutation qualification, exact verification, deviations (none unless literal), reviewer focus, and remaining risks. Do not reference local workflow scratch documents in a PR description.

- [x] **Step 5: Reconcile the publication stop and later authorization**

The exact pre-authorization stop was recorded in commit `83bd018b` while that
boundary still applied. The maintainer's later exact statement `authorize
remaining steps` superseded that stop and authorized the remaining publication,
hosted-evidence, and approved artifact-versioning steps. The current instruction
adds a narrower operational hold: no remote action before parent final review.
The results ledger records both facts without treating this document as a source
of permission.

- [x] **Step 6: Freeze the executable SHA, then commit local evidence**

The approved polish correction is the executable authority. Freeze it before the
evidence-only commit, then stage only the three approved documentation artifacts:

```bash
FROZEN_EXECUTABLE_HEAD=$(git rev-parse HEAD)
test "$FROZEN_EXECUTABLE_HEAD" = \
  "83bd018b6eeb29e159741258e8d979c7481d7d01"
git status --short
git diff --check
git diff --cached --check
git diff --check 463bccb0..HEAD
git add \
  docs/superpowers/specs/2026-09-26-ci-broad-waste-reduction-stage-a-design.md \
  docs/superpowers/plans/2026-09-26-ci-broad-waste-reduction-stage-a.md \
  docs/ci-broad-waste-reduction-stage-a-results.md
git diff --cached --name-only
git commit -m "test: finalize broad CI waste reduction Stage A"
test -z "$(git status --porcelain=v2 --untracked-files=all)"
EVIDENCE_HEAD=$(git rev-parse HEAD)
test "${#EVIDENCE_HEAD}" -eq 40
printf 'FROZEN_EXECUTABLE_HEAD=%s\nEVIDENCE_HEAD=%s\n' \
  "$FROZEN_EXECUTABLE_HEAD" "$EVIDENCE_HEAD"
```

Before commit, assert staged paths are exactly the three documentation paths,
a nonempty subset of the eight-path tranche; total `463bccb0..HEAD` paths remain
exactly the eight approved paths. The frozen executable SHA is the implementation
authority. A later publication uses the final evidence head while separately
proving that its five executable test paths are byte-identical to the frozen
executable head.

- [x] **Step 7: STOP**

Return the frozen executable SHA, evidence commit, exact checks, structural
results, scope, and concerns. Do not push, open/update a PR, query or mutate
remote state, dispatch/rerun Actions, or download candidate artifacts until the
parent final reviewer completes review. Publication is authorized but held by the
current instruction.

- [ ] **Step 8: After parent final review, verify remote state before acting**

Publication authorization is already present, but the current hold must first be
released. Use explicit runtime inputs in every command. Here `REVIEWED_HEAD` is
the final evidence head actually published; retain the separate frozen executable
SHA and require the five executable test paths to be byte-identical between them.

```bash
REPOSITORY=elboaf/FlyGD-Wingman
: "${FROZEN_EXECUTABLE_HEAD:?literal frozen executable head is required}"
: "${REVIEWED_HEAD:?literal authorized 40-character publication head is required}"
: "${RUN_ID:?literal authorized workflow run ID is required}"
: "${PR_NUMBER:?literal authorized pull request number is required}"
test "$(git rev-parse HEAD)" = "$REVIEWED_HEAD"
test -z "$(git status --porcelain=v2 --untracked-files=all)"
git log -5 --oneline --decorate
gh pr view "$PR_NUMBER" -R "$REPOSITORY" \
  --json number,state,mergedAt,headRefOid,baseRefOid,headRefName,baseRefName,url
gh api "repos/$REPOSITORY/actions/runs/$RUN_ID"
```

Never amend an already merged PR. Require target `main`, PR head equal to `REVIEWED_HEAD`, and no inferred “latest” run. Never use `--no-verify`.

- [ ] **Step 9: Collect hosted evidence with logs-primary synthetic binding**

The hosted collector takes mandatory literal `REVIEWED_HEAD`, `RUN_ID`, and `PR_NUMBER` and begins with this executable binding—no default, current branch, or latest-run inference:

```python
import json
import os
import re
import subprocess
from pathlib import Path

REPOSITORY = "elboaf/FlyGD-Wingman"
W = Path("/mnt/c/dev/flygd-wingman/.worktrees/ci-broad-waste-stage-a")
REVIEWED_HEAD = os.environ["REVIEWED_HEAD"]
RUN_ID = int(os.environ["RUN_ID"])
PR_NUMBER = int(os.environ["PR_NUMBER"])
assert re.fullmatch(r"[0-9a-f]{40}", REVIEWED_HEAD)


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def gh_json(*args: str):
    return json.loads(command("gh", *args))


assert command("git", "-C", str(W), "rev-parse", "HEAD") == REVIEWED_HEAD
assert command(
    "git", "-C", str(W), "status", "--porcelain=v2", "--untracked-files=all"
) == ""
run = gh_json("api", f"repos/{REPOSITORY}/actions/runs/{RUN_ID}")
pr = gh_json(
    "pr",
    "view",
    str(PR_NUMBER),
    "-R",
    REPOSITORY,
    "--json",
    "number,state,mergedAt,headRefOid,baseRefOid,headRefName,baseRefName,url",
)
assert pr["number"] == PR_NUMBER
assert pr["state"] == "OPEN" and pr["mergedAt"] is None
assert pr["headRefOid"] == run["head_sha"] == REVIEWED_HEAD
assert pr["baseRefName"] == "main"
```

It must then:

1. fetch run JSON and every attempt JSON; record failures/reruns rather than replacing history;
2. require event `pull_request`, completed success, run head and PR `headRefOid` equal `REVIEWED_HEAD`;
3. select exactly checks, Ubuntu, and Windows jobs for the selected attempt and require each job head equal the reviewed SHA;
4. download each job log and parse exactly one checkout line `HEAD is now at <synthetic-short> Merge <head40> into <base40>` plus the subsequent `git log -1 --format=%H`; require all three logs agree;
5. fetch the synthetic commit and execute this exact parent assertion (the `rev-list --parents` output includes the commit itself):

```python
SYNTHETIC, HEAD, BASE = checkout_log_tuple
assert HEAD == REVIEWED_HEAD
subprocess.run(
    ["git", "-C", str(W), "fetch", "--quiet", "--no-tags", "origin", SYNTHETIC, BASE, REVIEWED_HEAD],
    check=True,
)
parents = command(
    "git",
    "-C",
    str(W),
    "rev-list",
    "--parents",
    "-n",
    "1",
    SYNTHETIC,
).split()
assert parents == [SYNTHETIC, BASE, REVIEWED_HEAD], parents
```

   If an implementation instead calls `git show --format=%P`, that parent-only array must equal `[BASE, REVIEWED_HEAD]`; never compare a parent-only array with the three-element `rev-list` form;
6. permit empty run `pull_requests` metadata only when explicit current PR data corroborates number/head/base; record it as `absent`, never guess;
7. select each artifact by exact name, run ID, reviewed head, job start/completion time window, non-expired status, and unique match;
8. verify API digest, ZIP SHA-256, exact two-member set, and extracted/member byte equality;
9. parse JUnit with the longest-module-prefix parser and require exact baseline 16,609 order/hash, `+0/-0` globally and per targeted file, exact platform outcomes/skips/hashes, and no failure/error/availability skip;
10. require exact Preview four, rolling one, changed eight, focused 27, 35-set, five-file 313, relevant 494, and platform identity order;
11. audit synthetic diff as exactly the eight allowed paths and all protected paths unchanged;
12. report targeted testcase sums, complete testcase sums, XML suite times, Test-step and job observations separately.

A failed/cancelled/missing-artifact attempt is `INCONCLUSIVE` or `STOP`, never retried silently to manufacture favorable timing. Hosted artifact/JUnit evidence is authoritative for outcomes; checkout logs are primary for synthetic/head/base provenance.

- [ ] **Step 10: Hosted conclusions and evidence-only commit**

Use only these classifications:

- `PASS` — exact identities/outcomes/skips/scope/provenance preserved;
- `INCONCLUSIVE` — missing/incomparable artifact, cancelled/failed unrelated run, or provenance cannot bind;
- `STOP` — identity/skip/scope/protected contract differs.

Report structural local evidence (`4` trigger uses/zero old waits, `2,101/197,136`, `32/105`) independently from hosted timing observations. Never state speedup, slowdown, lower bound, p95, runner efficiency, or critical-path causation from one run.

If authorized, commit only the evidence update:

```bash
git add docs/ci-broad-waste-reduction-stage-a-results.md
git diff --cached --name-only
git commit -m "docs: record hosted Stage A evidence"
```

Do not push that evidence commit without a second explicit authorization covering its SHA.

---

## Plan-Author Disposable Validation

This plan was assembled and exercised against a disposable archive of `463bccb0` at `/tmp/wingman-stage-a-plan-candidate`; no candidate implementation was written to the repository worktree.

- the relevant selection passed all `494` unchanged identities;
- the eight `runtime_pump` consumer files passed all `388` identities;
- the focused presentation/geometry/timing/shoot selection passed `293` identities;
- all 18 temporary observer cases passed, including direct/composed legacy semantics, deterministic waiter-side premature-notify control, the terminal error/disarm race, owned cleanup after wait interruption, replacement preservation after wait interruption, and explicit cleanup-failure chaining;
- literal RED collected the exact four production IDs and failed each only at `trigger wait not implemented`, with no import/collection error;
- 8 observer mutants, 9 timing mutants, and 14 screenshot mutants each failed their exact intended ID/assertion and restored bytes/hash/binary diff/NUL status; the screenshot set includes non-Preview `fittings-narrow` floor omission and delayed-set reversal witnesses owned by the full traversal;
- the external JUnit parser resolved all 18 one-component-classname observer IDs through an explicit collection map and preserved outcome/phase/message/traceback without duplicates;
- the identity/signature gate preserved all 313 IDs/markers/decorators and allowed exactly the four named receipt-consumer substitutions;
- restoration simulation proved a restored probe rethrows its original sentinel and a deliberate restoration mismatch stops the matrix while chaining that sentinel;
- timing instrumentation observed baseline `2,101/2,101/2,208,151` and candidate `2,101/2,101/197,136` candidate/commit/check counts;
- baseline screenshot instrumentation observed 35 walks/515 visits;
- candidate normal, reverse-block, and seed-`20260926` orders each observed 35 passing IDs, one receipt construction, 32 walks, and 105 visits with exact hashes;
- the four immutable-receipt consumers passed together (`4 passed`) and each passed in its own separate direct-selection process;
- the mixed order passed all 35 IDs and observed four fixture constructions/35 walks/108 visits, retained only as diagnostic confirmation that cross-module counts are not acceptance evidence;
- static inspection found trigger-helper calls exactly at presentation lines 59/196 and geometry lines 172/210 in the disposable formatted candidate, with unchanged `eve_on()` hash;
- all disposable assembly/probe/instrumentation scripts passed `py_compile`, Ruff check, and Ruff format check;
- the five candidate test files passed Ruff check/format; repository documentation tests passed `7` cases.

These are plan qualification facts, not implementation acceptance or elapsed-performance evidence. Tasks 1–5 rerun every applicable gate from the actual committed implementation.

## Stop Conditions

Stop and return to design review if any approved-spec stopping rule triggers, especially if:

1. production callback semantics, production timing, `shoot.walk()`, `SCREENS`, workflow/config/dependencies, or a sixth test file must change;
2. Preview cannot arm atomically before trigger, preserve exact delegate return/error identity, prioritize every armed error, restore owned-only without replay on every trigger/wait/terminal `BaseException` exit, or expose cleanup failure without replacing the original body exception;
3. `eve_on()` changes or trigger-helper calls differ from exactly four;
4. timing transitions/commits differ from 2,101 or oracle checks differ from 197,136;
5. any timing mutant survives or fails only at defensive overflow/later masking;
6. safe screenshot orders differ from one construction/32 walks/105 visits, or mixed interleaving is misreported as count evidence;
7. exact 61/14, two Preview setup screens, one success order, one failure order, or exact 13 Fittings screens are lost;
8. any observer/timing/screenshot mutation survives its intended assertion;
9. restoration cannot reproduce bytes/hash/binary diff/NUL status;
10. exact 16,609 identity order, outcomes, normalized skips, markers, or protected scope differs;
11. Node/codec/unexpected native skips occur;
12. evidence supports only elapsed attribution rather than structural contract preservation.

## Plan Self-Review Checklist

Before committing this plan, confirm:

- exactly five tasks exist and map every approved spec section;
- permanent snippets use current symbols/imports and exact four call sites;
- exact IDs, counts, hashes, selectors, inventories, arithmetic, observations, and protected hashes are internally consistent;
- legacy/trigger Preview contracts, error precedence, current-state completion, replacement, sequential/concurrent cleanup, outer exceptional-exit coverage, exact `BaseException` identity, cleanup-failure chaining, no marked-wrapper leak, and exact five-second bound are explicit;
- timing expected input is independent and all nine mutations have intended witnesses;
- screenshot selector, 61 keys, 14 exact floor intervals, 13 Fittings, immutable receipt, 35-ID orders, 14 original mutations, and the deferred-clear mutation are explicit;
- JUnit per-ID intended-failure parsing rejects masking and timeouts;
- restoration compares bytes/hash/binary diff/NUL status;
- complete prerequisites/tests/Node/Cargo/Ruff/docs/scope commands are explicit;
- hosted collection is explicit-input, rerun-aware, logs-primary, synthetic-parent-bound, artifact-windowed, and exact-identity/skip scoped;
- no placeholder, projected speedup, Stage B/C work, implementation, actual subagent dispatch, or push occurred while revising this planning commit; the future review fallback is explicitly authorization-gated.
