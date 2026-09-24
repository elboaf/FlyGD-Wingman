# Setup Controller Fixture Construction Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace only the four brand-new initial DAT publications performed by the repeated setup-controller fixture with an exclusive fresh-file publisher, preserving codec verification, all 188 existing controller identities, every controller-body atomic persistence boundary, and all non-controller callers' atomic defaults.

**Architecture:** Add one private test-only `(Path, bytes) -> None` publisher in `tests/setup_fixtures.py` and expose it only through a keyword-only `seed_profile(..., initial_dat_publish=None)` seam whose `None` branch omits the codec `publish` override. Qualify parity, isolation, syscall shape, failure cleanup, separate direct/atomic fsync channels, and controller-body persistence in exactly two appended non-parameterized witnesses; only then opt the existing two-argument controller `setup` fixture into the fresh publisher for its source and recipient profiles.

**Tech Stack:** Python 3.11, pytest, stdlib `os`/`pathlib`/`stat`/`xml.etree.ElementTree`, the existing lossless and native settings codec paths, Node.js setup-page harness, Cargo settings codec, uv, Git, and GitHub Actions JUnit/timing artifacts.

**Spec:** `docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md`

## Global Constraints

- Source baseline is merged `main` commit `c23788e3` (`Consolidate generated verifier and Alerts tests (#287)`).
- Preserve all 188 existing `tests/test_ui_setup_controller.py` testcase identities byte-for-text and in their existing order.
- Add exactly two non-parameterized witness identities, appended after the existing collection so the ordered 188-ID baseline remains the exact prefix.
- The exact witness suffix, in order, is:
  1. `tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures`
  2. `tests/test_ui_setup_controller.py::test_fast_fixture_construction_preserves_controller_body_atomic_persistence`
- Exactly the original 136 controller cases continue to consume the pytest `setup` fixture; neither new witness requests it.
- The structural claim is only `136 × 2 profiles × 2 DATs = 544` fixture-construction fsync calls removed.
- Make no Windows, Linux, suite, job, runner-efficiency, critical-path, or wall-clock speedup claim.
- `seed_profile()` remains atomic by default. `initial_dat_publish=None` means omit `publish=` and retain `codec.write_document()`'s existing definition-time default.
- Only the existing controller `setup(tmp_path, monkeypatch)` fixture opts reusable construction into the fresh publisher. Its signature and positional order do not change because `tests/fixtures/ui_setup_page.cjs` calls `setup.__wrapped__(Path(temp), patch)`.
- The two qualification witnesses may call the private helper, `seed_profile()`, or `setup.__wrapped__()` directly; no other existing reusable fixture or caller opts in.
- The fresh helper makes exactly one destination creation call: `os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)`.
- The helper performs no existence/stat/access preflight, fsync, tempfile creation, replace, retry, hardlink, reflink, symlink, shared template, or session cache.
- The helper loops through legal partial writes, rejects zero progress, closes before success, removes a partial destination after write/close failure where possible, and re-raises the original failure object.
- Codec encode, signature validation, verifying decode, envelope equality, `had_crc`, and revision computation remain real for fast construction.
- Controller-body staging, rewritten DAT publication, final directory publication, and selection persistence remain production-strength and atomic.
- Temporary mutants are uncommitted, match-once, fail only at their intended witness assertion, and are restored exactly after every probe.
- Node and the built release settings codec are mandatory for full verification; availability skips are not acceptable evidence.
- Exact committed tranche scope is limited to:
  - `docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md`
  - `docs/superpowers/plans/2026-09-24-setup-controller-fixture-construction.md`
  - `docs/ci-setup-controller-fixture-construction-results.md`
  - `tests/setup_fixtures.py`
  - `tests/test_ui_setup_controller.py`
- No file under `wingman/`, other test module, Node fixture, workflow, dependency, lockfile, packaging path, pytest configuration, marker, selector, budget, or shard manifest may be committed.
- Stop and return to design review if production changes, replacement support, a reusable opt-in outside the controller fixture, another test module, more than two identities, fixture signature changes, shared templates, or weakened controller persistence become necessary.

## File Structure and Ownership

- Create `docs/ci-setup-controller-fixture-construction-results.md` as the sole evidence ledger for baseline identities, structural fixture-use inventory, PR #287 artifact provenance, mutation outcomes, local verification, hosted comparison, scope, concerns, and self-review.
- Modify `tests/setup_fixtures.py` to own `_publish_fresh_file(path, data)` and the optional `seed_profile(..., initial_dat_publish=None)` seam. This file does not know about controllers or instrumentation.
- Modify `tests/test_ui_setup_controller.py` to import the fixture module itself, opt only `setup` into `_publish_fresh_file`, add test-local proxies/normalizers, and append the exact two witness tests.
- Read but do not commit changes to `wingman/evesettings/codec.py`, `setup_profile.py`, `profilecopy.py`, `controller.py`, `wingman/atomicio.py`, and `wingman/settings.py`; temporary mutation probes against `setup_profile.py` are restored before any commit.
- Keep `tests/test_ui_setup_schema.py`, `tests/test_ui_setup_profile.py`, `tests/test_ui_setup_integration.py`, `tests/test_evesettings_codec.py`, `tests/test_evesettings_profilecopy.py`, `tests/test_atomicio.py`, `tests/test_ui_setup_page.py`, and `tests/fixtures/ui_setup_page.cjs` unchanged; their default paths and direct wrapped-fixture call are acceptance evidence.

## Task Right-Sizing

1. Task 1 freezes source/artifact truth and creates the results ledger without accepting a helper or executable change.
2. Task 2 adds and independently qualifies the private publisher, optional seed seam, and comprehensive witness while every existing caller remains atomic.
3. Task 3 opts only the controller fixture into the helper and adds the independently reviewable controller-body persistence witness.
4. Task 4 proves the complete local endpoint, exact 188-prefix/2-suffix identity transformation, full-suite projection, skips, gates, scope, and mutation restoration.
5. Task 5 performs polish, whole-branch review, change explanation, an explicit publication stop, and—only after authorization—the hosted Windows/Ubuntu comparison against PR #287.

## Plan-Author Baseline Check

The plan author independently collected the current baseline and reparsed `/tmp/wingman-stage3-{windows,ubuntu}`. The observed authorities match the approved design: 188 controller identities, 136 structural users of fixture `setup`, 16,605 complete identities, 14 Ubuntu skips, 67 Windows skips, controller testcase sums 3.185s/42.301s, setup-user sums 2.964s/40.384s, and other-controller sums 0.221s/1.917s. Per the spec, this plan publishes no projected controller or full-suite node hash; implementation computes hashes from actual newline-terminated inventories.

---

## Reproducibility Blocks

### Block A — exact baseline identities, structural fixture users, and PR #287 artifacts

This block extracts `c23788e3` into a disposable checkout, uses a pytest collection plugin to identify `setup` consumers structurally through `item.fixturenames`, writes one complete node ID per line with a final newline, and reparses both hosted artifacts. It writes only under `/tmp`.

```bash
cat > /tmp/setup_fixture_inventory_plugin.py <<'PY'
from __future__ import annotations
import json, os
from pathlib import Path


def pytest_collection_finish(session):
    rows = [
        {"nodeid": item.nodeid, "uses_setup": "setup" in item.fixturenames}
        for item in session.items
    ]
    Path(os.environ["WINGMAN_COLLECTION_OUT"]).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
PY
cat > /tmp/setup_fixture_baseline.py <<'PY'
from __future__ import annotations
import hashlib, io, json, os, re, subprocess, tarfile, tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

W = Path('/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit')
P = W / '.venv/bin/python'
O = Path('/tmp/wingman-setup-fixture-baseline')
ARTIFACTS = {
    'ubuntu': Path('/tmp/wingman-stage3-ubuntu'),
    'windows': Path('/tmp/wingman-stage3-windows'),
}
CONTROLLER = 'tests/test_ui_setup_controller.py'


def sha(nodes):
    return hashlib.sha256(('\n'.join(nodes) + '\n').encode()).hexdigest()


def extract(commit, root):
    raw = subprocess.check_output(['git', '-C', str(W), 'archive', commit])
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        archive.extractall(root, filter='data')


def collect(root, args, name):
    output = O / name
    env = dict(os.environ, PYTHONPATH=f"{root}:/tmp", WINGMAN_COLLECTION_OUT=str(output))
    run = subprocess.run(
        [str(P), '-m', 'pytest', *args, '--collect-only', '-q',
         '-p', 'no:cacheprovider', '-p', 'setup_fixture_inventory_plugin'],
        cwd=root, env=env, text=True, capture_output=True, timeout=240,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    rows = json.loads(output.read_text(encoding='utf-8'))
    nodes = [row['nodeid'] for row in rows]
    assert len(nodes) == len(set(nodes))
    return rows


def identity(case):
    parts = case.get('classname').split('.')
    assert len(parts) >= 2 and parts[0] == 'tests', parts
    return '::'.join(('/'.join(parts[:2]) + '.py', *parts[2:], case.get('name')))


def normalized_skip(text):
    return re.sub(
        r'pytest-of-[^/\s]+/pytest-\d+/[^\s:\"\']+',
        'pytest-of-<USER>/pytest-<N>/<PYTEST_TMP>',
        text.replace('\\', '/'),
    )


def artifact(root):
    cases = list(ET.parse(root / 'pytest-result.xml').getroot().iter('testcase'))
    ids = [identity(case) for case in cases]
    assert len(ids) == len(set(ids))
    seconds = {node: float(case.get('time', '0') or 0)
               for node, case in zip(ids, cases, strict=True)}
    skips = []
    failures = errors = 0
    counts = defaultdict(int)
    sums = defaultdict(float)
    for node, case in zip(ids, cases, strict=True):
        file = node.split('::', 1)[0]
        counts[file] += 1
        sums[file] += seconds[node]
        skipped = case.find('skipped')
        if skipped is not None:
            skips.append((node, normalized_skip(skipped.get('message') or skipped.text or '')))
        failures += len(case.findall('failure'))
        errors += len(case.findall('error'))
    timing = json.loads((root / 'pytest-timing.json').read_text(encoding='utf-8'))
    assert timing['case_count'] == len(ids)
    for file, row in timing['files'].items():
        assert row['cases'] == counts[file]
        assert abs(row['seconds'] - sums[file]) < 1e-9
    return ids, seconds, skips, failures, errors

O.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='wingman-setup-baseline-') as directory:
    root = Path(directory)
    extract('c23788e3', root)
    controller_rows = collect(root, [CONTROLLER], 'controller-collection.json')
    complete_rows = collect(root, ['tests'], 'complete-collection.json')
controller = [row['nodeid'] for row in controller_rows]
setup_users = [row['nodeid'] for row in controller_rows if row['uses_setup']]
complete = [row['nodeid'] for row in complete_rows]
assert len(controller) == 188
assert len(setup_users) == 136
assert len(complete) == 16605
parsed = {platform: artifact(path) for platform, path in ARTIFACTS.items()}
ubuntu_ids, ubuntu_time, ubuntu_skips, uf, ue = parsed['ubuntu']
windows_ids, windows_time, windows_skips, wf, we = parsed['windows']
assert ubuntu_ids == complete
assert set(windows_ids) == set(complete)
assert uf == ue == wf == we == 0
assert len(ubuntu_skips) == 14 and len(windows_skips) == 67
assert [node for node in ubuntu_ids if node.startswith(CONTROLLER + '::')] == controller
assert [node for node in windows_ids if node.startswith(CONTROLLER + '::')] == controller
setup_set = set(setup_users)
for name, nodes in {
    'controller-188.txt': controller,
    'setup-users-136.txt': setup_users,
    'complete-16605.txt': complete,
}.items():
    (O / name).write_text('\n'.join(nodes) + '\n', encoding='utf-8')
for platform, skips in {'ubuntu': ubuntu_skips, 'windows': windows_skips}.items():
    (O / f'{platform}-skips.json').write_text(
        json.dumps(skips, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {
    'controller_count': len(controller),
    'controller_sha256': sha(controller),
    'setup_user_count': len(setup_users),
    'setup_user_sha256': sha(setup_users),
    'complete_count': len(complete),
    'complete_sha256': sha(complete),
    'ubuntu_controller_seconds': sum(ubuntu_time[node] for node in controller),
    'windows_controller_seconds': sum(windows_time[node] for node in controller),
    'ubuntu_setup_seconds': sum(ubuntu_time[node] for node in setup_users),
    'windows_setup_seconds': sum(windows_time[node] for node in setup_users),
    'ubuntu_other_seconds': sum(ubuntu_time[node] for node in controller if node not in setup_set),
    'windows_other_seconds': sum(windows_time[node] for node in controller if node not in setup_set),
    'ubuntu_skips': len(ubuntu_skips),
    'windows_skips': len(windows_skips),
}
(O / 'summary.json').write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n')
print(json.dumps(summary, sort_keys=True))
PY
python -m py_compile /tmp/setup_fixture_inventory_plugin.py /tmp/setup_fixture_baseline.py
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit
uv run --no-sync python /tmp/setup_fixture_baseline.py
```

Expected: exact counts 188, 136, and 16,605; Ubuntu/Windows complete identity sets equal; no controller skips; 14/67 platform skips; zero failures/errors; the timing observations in the approved spec; actual hashes written to `summary.json`, not predicted in this plan.

### Block B — match-once mutation apply and restore

Every repository mutation probe uses this driver. Each before and after body is supplied in named `/tmp` files by the owning task. `check`, `apply`, and `restore` all require an exact single match and the restore returns the original bytes.

```bash
cat > /tmp/setup_fixture_guarded_replace.py <<'PY'
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=('check', 'apply', 'restore'))
parser.add_argument('target', type=Path)
parser.add_argument('before', type=Path)
parser.add_argument('after', type=Path)
parser.add_argument('backup', type=Path)
args = parser.parse_args()
before = args.before.read_text(encoding='utf-8')
after = args.after.read_text(encoding='utf-8')
assert before and after and before != after
if args.mode in ('check', 'apply'):
    text = args.target.read_text(encoding='utf-8')
    assert text.count(before) == 1, ('before_count', text.count(before))
    changed = text.replace(before, after, 1)
    assert changed.count(after) == 1, ('after_count', changed.count(after))
    if args.mode == 'check':
        print(json.dumps({'before_count': 1, 'after_count': 1}))
    else:
        assert not args.backup.exists()
        args.backup.write_bytes(args.target.read_bytes())
        args.target.write_text(changed, encoding='utf-8')
        print(json.dumps({'original_sha256': hashlib.sha256(args.backup.read_bytes()).hexdigest()}))
else:
    assert args.backup.is_file()
    text = args.target.read_text(encoding='utf-8')
    assert text.count(after) == 1, ('after_count', text.count(after))
    original = args.backup.read_bytes()
    assert original.decode('utf-8').count(before) == 1
    args.target.write_bytes(original)
    args.backup.unlink()
    print(json.dumps({'restored_sha256': hashlib.sha256(original).hexdigest()}))
PY
python -m py_compile /tmp/setup_fixture_guarded_replace.py
```

For every mutation row:

```bash
python /tmp/setup_fixture_guarded_replace.py check TARGET /tmp/before.txt /tmp/after.txt /tmp/MUTANT.backup
python /tmp/setup_fixture_guarded_replace.py apply TARGET /tmp/before.txt /tmp/after.txt /tmp/MUTANT.backup
# Run the exact witness command and save the intended assertion.
python /tmp/setup_fixture_guarded_replace.py restore TARGET /tmp/before.txt /tmp/after.txt /tmp/MUTANT.backup
git diff --exit-code -- TARGET
```

### Block C — final identity and scope audit

After Task 3, collect actual controller and full-suite identities and compare them to Block A. The script refuses any baseline removal, rename, reorder, additional suffix, structural setup-fixture-user change, or unapproved path.

```bash
cat > /tmp/setup_fixture_endpoint_audit.py <<'PY'
from __future__ import annotations
import hashlib, json, os, subprocess
from pathlib import Path

W = Path('/mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit')
P = W / '.venv/bin/python'
B = Path('/tmp/wingman-setup-fixture-baseline')
O = Path('/tmp/wingman-setup-fixture-endpoint')
O.mkdir(exist_ok=True)
CONTROLLER = 'tests/test_ui_setup_controller.py'
SUFFIX = [
    CONTROLLER + '::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures',
    CONTROLLER + '::test_fast_fixture_construction_preserves_controller_body_atomic_persistence',
]


def sha(nodes):
    return hashlib.sha256(('\n'.join(nodes) + '\n').encode()).hexdigest()


def collect(args, output):
    env = dict(os.environ, PYTHONPATH=f"{W}:/tmp", WINGMAN_COLLECTION_OUT=str(output))
    run = subprocess.run(
        [str(P), '-m', 'pytest', *args, '--collect-only', '-q',
         '-p', 'no:cacheprovider', '-p', 'setup_fixture_inventory_plugin'],
        cwd=W, env=env, text=True, capture_output=True, timeout=240,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(output.read_text(encoding='utf-8'))

baseline_controller = (B / 'controller-188.txt').read_text().splitlines()
baseline_setup = (B / 'setup-users-136.txt').read_text().splitlines()
baseline_complete = (B / 'complete-16605.txt').read_text().splitlines()
controller_rows = collect([CONTROLLER], O / 'controller-collection.json')
complete_rows = collect(['tests'], O / 'complete-collection.json')
controller = [row['nodeid'] for row in controller_rows]
setup_users = [row['nodeid'] for row in controller_rows if row['uses_setup']]
complete = [row['nodeid'] for row in complete_rows]
assert len(controller) == len(set(controller)) == 190
assert controller[:188] == baseline_controller
assert controller[188:] == SUFFIX
assert setup_users == baseline_setup
assert len(complete) == len(set(complete)) == 16607
assert set(baseline_complete) <= set(complete)
assert [node for node in complete if node not in set(baseline_complete)] == SUFFIX
assert not (set(baseline_complete) - set(complete))
for name, nodes in {
    'controller-190.txt': controller,
    'setup-users-136.txt': setup_users,
    'complete-16607.txt': complete,
    'added-2.txt': SUFFIX,
}.items():
    (O / name).write_text('\n'.join(nodes) + '\n', encoding='utf-8')
allowed = {
    'docs/ci-setup-controller-fixture-construction-results.md',
    'docs/superpowers/plans/2026-09-24-setup-controller-fixture-construction.md',
    'docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md',
    'tests/setup_fixtures.py',
    'tests/test_ui_setup_controller.py',
}
changed = set(subprocess.check_output(
    ['git', '-C', str(W), 'diff', '--name-only', 'c23788e3..HEAD'], text=True
).splitlines())
assert changed <= allowed, sorted(changed - allowed)
assert {'tests/setup_fixtures.py', 'tests/test_ui_setup_controller.py'} <= changed
summary = {
    'controller_count': len(controller),
    'controller_sha256': sha(controller),
    'setup_user_count': len(setup_users),
    'setup_user_sha256': sha(setup_users),
    'complete_count': len(complete),
    'complete_sha256': sha(complete),
    'added': SUFFIX,
    'removed': [],
    'changed_paths': sorted(changed),
}
(O / 'summary.json').write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n')
print(json.dumps(summary, sort_keys=True))
PY
python -m py_compile /tmp/setup_fixture_endpoint_audit.py
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit
uv run --no-sync python /tmp/setup_fixture_endpoint_audit.py
```

Expected: 190 controller IDs with exact 188 prefix and exact two-ID suffix, unchanged 136 structural setup users, 16,607 complete IDs, two additions, zero removals, and only the five approved paths.

---

### Task 1: Freeze the c23788e3 Baseline and Create the Evidence Ledger

**Files:**
- Create: `docs/ci-setup-controller-fixture-construction-results.md`
- Read: `docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md`
- Read: `tests/setup_fixtures.py`
- Read/collect: `tests/test_ui_setup_controller.py`
- Read artifacts: `/tmp/wingman-stage3-ubuntu/{pytest-result.xml,pytest-timing.json}`
- Read artifacts: `/tmp/wingman-stage3-windows/{pytest-result.xml,pytest-timing.json}`

**Interfaces:**
- Consumes: source commit `c23788e3`, fixture name `setup`, PR #287 run `35994945673` attempt 2, Ubuntu job `107621270623`, Windows job `107621270652`, synthetic merge `ab2028f55f080e6067d7cc62002451f96171fa68`, PR head `db2185768b919331c54370d3532215e53d5583bd`, and base `8d5b93058d9de3def9c17d222ba2d665eb0ba87b`.
- Produces: exact ordered 188-controller, 136-setup-user, and 16,605-complete inventories; actual hashes; complete normalized skip tuples; artifact provenance/integrity; timing observations; and the results-document structure consumed by Tasks 2–5.

**Independent deliverable:** A reviewer can accept baseline truth and artifact attribution without accepting any helper, witness, or optimization.

- [ ] **Step 1: Verify checkout identity and artifact presence**

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit
git status --short --branch
git merge-base --is-ancestor c23788e3 HEAD
for platform in ubuntu windows; do
  test -f "/tmp/wingman-stage3-$platform/pytest-result.xml"
  test -f "/tmp/wingman-stage3-$platform/pytest-timing.json"
done
node --version
uv sync --locked --extra dev
```

Expected: branch `ci-setup-fixture-construction`, clean except approved planning history, `c23788e3` is an ancestor, both artifact roots contain exactly the required evidence files, Node is available, and dependency sync succeeds.

- [ ] **Step 2: Run Block A and freeze all ordered inventories**

Run Block A exactly.

Expected:

- exactly 188 unique controller IDs;
- exactly 136 IDs whose collected `item.fixturenames` contains `setup`;
- exactly 16,605 unique complete-suite IDs;
- controller IDs in both artifact sets equal the source collection in order;
- Ubuntu and Windows complete identity sets equal;
- zero failures/errors;
- 14 Ubuntu and 67 Windows normalized skip tuples;
- actual newline-normalized SHA-256 values recorded from generated files, never copied from this plan.

- [ ] **Step 3: Record exact artifact identity and provenance**

Record these approved attempt-2 authorities and verify extracted file hashes directly:

| Platform | Job | Artifact ID | Archive digest | XML SHA-256 | Timing SHA-256 |
|---|---:|---:|---|---|---|
| Ubuntu | `107621270623` | `10806746306` | `sha256:ae44499ef75418f94fc220351e30cd8bbba35709d89d8f76737cc0a7fef6a17f` | `40e3c887f72c1332cf0ebbcd31716c5bce63d60e776d6c8e0437a3b8ecb690ff` | `ece3c88211a0e00bc29fbcfa0d052c1a5e02296386984c75e65d9a4c5519157c` |
| Windows | `107621270652` | `10807115906` | `sha256:0249528a74786639791c9386c1dafe41cd93abb667682efd25b25de7e885606b` | `24875479dcd8d146251b605a44733d9afaf0656e64d16273aade3c56da31c8be` | `b8a929884c1550a92464124eabe0ade06f33202a0e00a117577acb12945b63ae` |

```bash
sha256sum /tmp/wingman-stage3-ubuntu/pytest-result.xml \
  /tmp/wingman-stage3-ubuntu/pytest-timing.json \
  /tmp/wingman-stage3-windows/pytest-result.xml \
  /tmp/wingman-stage3-windows/pytest-timing.json
```

Expected: extracted hashes match the table. Record that attempt 1 is excluded and attempt 2 is passing comparator evidence.

- [ ] **Step 4: Record exact timing and skip controls without making a speed claim**

Publish the complete ordered normalized skip tuples from Block A and these JUnit observations:

| Scope | Ubuntu | Windows |
|---|---:|---:|
| Complete identities | 16,605 | 16,605 |
| Passed | 16,591 | 16,538 |
| Intentional platform skips | 14 | 67 |
| Controller identities | 188 | 188 |
| Controller skips | 0 | 0 |
| Controller testcase sum | 3.185s | 42.301s |
| Structural `setup` users | 136 | 136 |
| Setup-user testcase sum | 2.964s | 40.384s |
| Other-controller testcase sum | 0.221s | 1.917s |

State that these observations motivate structural filesystem analysis but prove no expected duration change.

- [ ] **Step 5: Create the results document with exact sections**

Create these top-level sections and populate Task 1 evidence completely:

1. `Scope and authority`
2. `Task status`
3. `Exact 188-ID controller baseline`
4. `Exact 136-ID structural setup-fixture inventory`
5. `Exact 16,605-ID complete baseline`
6. `PR #287 attempt-2 provenance and artifact integrity`
7. `Complete normalized comparator skip tuples`
8. `Comparator testcase observations`
9. `Fresh publisher and parity evidence`
10. `Controller-body persistence evidence`
11. `Mutation ledger and restoration`
12. `Local endpoint verification`
13. `Hosted comparison`
14. `Deviations and concerns`
15. `Required self-review`

For later sections use explicit status text such as `NOT STARTED — Task 2 owns this evidence`; do not use an unfinished-body marker or imply evidence already exists.

- [ ] **Step 6: Audit and commit Task 1**

```bash
git diff --check
git diff --name-only
git add docs/ci-setup-controller-fixture-construction-results.md
git commit -m "docs: freeze setup fixture construction baseline"
```

Expected: only the results document is committed in this task.

**Implementer report:** Commit SHA; exact counts and actual hashes; complete artifact provenance and extracted hashes; 14/67 skips; timing table; changed paths; and discrepancies. State explicitly that no executable file or test identity changed.

**Fresh reviewer gate:** Independently rerun Block A, compare every inventory byte-for-byte, recompute hashes, reparse both artifact sets and timing JSON, verify structural fixture use rather than name-pattern inference, and approve the Task 1 commit.

**Fix loop:** Any identity, fixture-use, artifact, skip, timing, or provenance mismatch stops the tranche. Correct the evidence or attribution, rerun all Task 1 checks, commit a documentation correction, and repeat fresh review before Task 2.

---

### Task 2: Add and Qualify the Fresh Publisher, Optional Seed Seam, and Comprehensive Witness

**Files:**
- Modify: `tests/setup_fixtures.py:10-15,121-151`
- Modify: `tests/test_ui_setup_controller.py:1-30` and append after the current last test
- Modify: `docs/ci-setup-controller-fixture-construction-results.md`
- Test only: `tests/test_ui_setup_schema.py`, unchanged default-path caller

**Interfaces:**
- Consumes: existing `codec.write_document(path, document, *, backup, publish=atomicio.write_bytes_atomic, ...)` and the current `ProfileFixture`/fixture document factories.
- Produces:
  - `_publish_fresh_file(path: Path, data: bytes) -> None` in `tests.setup_fixtures`;
  - `seed_profile(tmp_path, *, case="recipient", name="Base", initial_dat_publish=None) -> ProfileFixture`;
  - exact appended witness `test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures`;
  - test-local `_OSProxy`, normalization, metadata, and seed-pair helpers in `tests/test_ui_setup_controller.py`.

**Independent deliverable:** The helper and first witness are fully qualified while the reusable controller fixture and every existing caller remain on the default atomic path.

- [ ] **Step 1: Add the witness name first and verify RED**

Append a minimal first version of the exact witness with signature `(tmp_path, monkeypatch)`—not `setup`—that imports `tests.setup_fixtures` and calls `_publish_fresh_file`.

```python
def test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures(
    tmp_path, monkeypatch
):
    target = tmp_path / "fresh.dat"
    setup_fixtures._publish_fresh_file(target, b"payload")
    assert target.read_bytes() == b"payload"
```

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures -q
```

Expected: FAIL with `AttributeError` because `_publish_fresh_file` does not exist.

- [ ] **Step 2: Implement the minimal helper with original-exception cleanup**

Add `import contextlib` and `import os` to `tests/setup_fixtures.py`, then add this helper immediately before `seed_profile`:

```python
def _publish_fresh_file(path: Path, data: bytes) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("Fresh fixture write made no progress.")
            remaining = remaining[written:]
        os.close(descriptor)
        descriptor = None
    except BaseException:
        if descriptor is not None:
            with contextlib.suppress(BaseException):
                os.close(descriptor)
        with contextlib.suppress(BaseException):
            os.unlink(path)
        raise
```

This shape is load-bearing:

- `os.open` is outside the cleanup `try`, so an existing destination is refused without unlinking it;
- the one syscall owns exclusivity;
- a close failure leaves `descriptor` non-`None`, so cleanup retries close and then unlinks;
- cleanup suppresses its own failure and the bare `raise` preserves the original exception object;
- no fsync, temporary neighbor, replace, retry, or preflight exists.

Run the focused witness. Expected: PASS for the initial success check.

- [ ] **Step 3: Add the optional seed seam while keeping omission observable**

Change the signature exactly to:

```python
def seed_profile(
    tmp_path,
    *,
    case="recipient",
    name="Base",
    initial_dat_publish=None,
) -> ProfileFixture:
```

Replace only the DAT write loop with an explicit branch that omits `publish` when `None`:

```python
    for path, document in ((account_path, account), (character_path, character)):
        # These files do not exist yet; there is no previous content to back up.
        if initial_dat_publish is None:
            codec.write_document(path, document, backup=lambda path: None)
        else:
            codec.write_document(
                path,
                document,
                backup=lambda path: None,
                publish=initial_dat_publish,
            )
```

Do not bind an atomic function or `_publish_fresh_file` as the default argument. Do not move YAML/INI writes through this publisher.

- [ ] **Step 4: Add robust module-binding proxies and exact normalizers**

In `tests/test_ui_setup_controller.py`, add `from collections import Counter`, `from dataclasses import asdict, fields, replace`, `import stat`, `from tests import setup_fixtures`, and `from wingman.evesettings import tree`. Preserve existing imports.

Add these test support definitions before the appended witness; they create no pytest identities:

```python
class _OSProxy:
    def __init__(self, real, *, assert_fresh_open=False, write_steps=(), close_error=None):
        self._real = real
        self._assert_fresh_open = assert_fresh_open
        self._write_steps = list(write_steps)
        self._close_error = close_error
        self._close_error_raised = False
        self.open_calls = []
        self.fsync_calls = []
        self.close_calls = 0
        self.unlink_calls = []
        self.preflight_calls = []

    def __getattr__(self, name):
        return getattr(self._real, name)

    def open(self, path, flags, mode=0o777):
        call = (Path(path), flags, mode)
        self.open_calls.append(call)
        if self._assert_fresh_open:
            expected = (
                self._real.O_CREAT
                | self._real.O_EXCL
                | self._real.O_WRONLY
                | getattr(self._real, "O_BINARY", 0)
            )
            assert flags == expected, f"fresh open flags changed: {flags:#x} != {expected:#x}"
            assert mode == 0o600, f"fresh open mode changed: {mode:o}"
        return self._real.open(path, flags, mode)

    def write(self, descriptor, data):
        if self._write_steps:
            step = self._write_steps.pop(0)
            if isinstance(step, BaseException):
                raise step
            if step == 0:
                return 0
            return self._real.write(descriptor, data[:step])
        return self._real.write(descriptor, data)

    def close(self, descriptor):
        self.close_calls += 1
        if self._close_error is not None and not self._close_error_raised:
            self._close_error_raised = True
            raise self._close_error
        return self._real.close(descriptor)

    def unlink(self, path):
        self.unlink_calls.append(Path(path))
        return self._real.unlink(path)

    def fsync(self, descriptor):
        self.fsync_calls.append(descriptor)
        return self._real.fsync(descriptor)

    def stat(self, *args, **kwargs):
        self.preflight_calls.append("os.stat")
        raise AssertionError("fresh publisher performed an os.stat preflight")

    def lstat(self, *args, **kwargs):
        self.preflight_calls.append("os.lstat")
        raise AssertionError("fresh publisher performed an os.lstat preflight")

    def access(self, *args, **kwargs):
        self.preflight_calls.append("os.access")
        raise AssertionError("fresh publisher performed an os.access preflight")


class _PathProxy:
    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        if name in {"exists", "lexists", "isfile", "isdir", "islink"}:
            raise AssertionError(f"fresh publisher performed os.path.{name} preflight")
        return getattr(self._real, name)


def _normalize_path(value, root):
    if isinstance(value, Path):
        return value.relative_to(root).as_posix()
    if isinstance(value, dict):
        return {key: _normalize_path(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_path(item, root) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_path(item, root) for item in value)
    return value


def _normalized_discovery(profile):
    found = asdict(tree.discover(profile.root, profile.server, profile.profile))
    for row in found["profiles"]:
        row.pop("modified")
    return _normalize_path(found, profile.root)


def _manifest(profile):
    found = tree.discover(profile.root, profile.server, profile.profile)
    plan = profilecopy.prepare_copy(found, profile.profile, "new", "ManifestTarget")
    return setup_profile.capture_manifest(plan)


def _normalized_manifest(profile):
    return _normalize_path(asdict(_manifest(profile)), profile.root)


def _inventory(profile):
    return {
        path.relative_to(profile.root).as_posix(): path.read_bytes()
        for path in sorted(profile.root.rglob("*"))
        if path.is_file()
    }


def _stable_file_metadata(path):
    info = path.stat()
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_size,
        info.st_nlink,
    )


def _seed_pair(root, publisher=None):
    kwargs = {} if publisher is None else {"initial_dat_publish": publisher}
    source = seed_profile(root, case="source", name="Source", **kwargs)
    recipient = seed_profile(root, **kwargs)
    return source, recipient
```

When installing a direct proxy, assign its `path` field to `_PathProxy(real_os.path)` before replacing `setup_fixtures.os`. Do not set attributes on the shared real `os` module.

- [ ] **Step 5: Expand the single witness into atomic-versus-fast parity and construction-fsync evidence**

The witness constructs atomic and fast source/recipient pairs in separate roots. Capture `real_os = os` before monkeypatching. Replace only `setup_fixtures.os` and `atomicio.os` with separate proxies. The test must execute these exact assertions:

```python
    install_lossless_codec(monkeypatch)
    real_os = os
    direct = _OSProxy(real_os, assert_fresh_open=True)
    direct.path = _PathProxy(real_os.path)
    atomic = _OSProxy(real_os)
    monkeypatch.setattr(setup_fixtures, "os", direct)
    monkeypatch.setattr(atomicio, "os", atomic)

    atomic_source, atomic_recipient = _seed_pair(tmp_path / "atomic")
    assert len(atomic.fsync_calls) == 4
    assert direct.fsync_calls == [] and direct.open_calls == []

    atomic.fsync_calls.clear()
    fast_source, fast_recipient = _seed_pair(
        tmp_path / "fast-a", setup_fixtures._publish_fresh_file
    )
    assert atomic.fsync_calls == [] and direct.fsync_calls == []
    assert len(direct.open_calls) == 4
    assert all(flags == real_os.O_CREAT | real_os.O_EXCL | real_os.O_WRONLY |
               getattr(real_os, "O_BINARY", 0) and mode == 0o600
               for _path, flags, mode in direct.open_calls)
    assert direct.preflight_calls == []
```

Then compare, for both source and recipient:

- full relative inventory and exact bytes;
- `codec.read_snapshot()` documents, `had_crc`, revisions, and `json.dumps(document.doc, ensure_ascii=False)` without `sort_keys` so mapping/list order and JSON type spelling remain visible;
- source IDs 10/11 and recipient IDs 20/30;
- source LF and recipient CRLF YAML/INI bytes;
- private sentinels;
- `_normalized_discovery()` with only root paths and `Profile.modified` normalized;
- `_normalized_manifest()` with only root paths normalized;
- manifest file names, sizes, hashes, and order.

Use exact preference expectations:

```python
    expected_preferences = {
        "source": {
            "core_public__.yaml": b"# synthetic source local preferences\nuiScale: 1.0\n",
            "prefs.ini": b"; synthetic source local preferences\nmonitor=1\n",
        },
        "recipient": {
            "core_public__.yaml": b"# synthetic recipient local preferences\r\nuiScale: 1.25\r\n",
            "prefs.ini": b"; synthetic recipient local preferences\r\nmonitor=2\r\n",
        },
    }
```

Expected: exact parity and default construction `4` atomic-channel fsyncs versus explicit fast construction `0` on both channels and four exact exclusive opens.

- [ ] **Step 6: Add isolation, metadata, duplicate, and no-template assertions in the same witness**

Create a second fast pair under `tmp_path / "fast-b"`. For every corresponding file:

```python
    assert first.is_file() and second.is_file()
    assert os.access(first, os.W_OK) and os.access(second, os.W_OK)
    assert first.stat().st_nlink == second.stat().st_nlink == 1
    assert not first.samefile(second)
```

Capture `_stable_file_metadata()` for all `fast-a` files, then run codec readback, discovery, and manifest capture and assert metadata remains byte-for-tuple unchanged. Do not compare atomic and fast inode/timestamps and do not record access/change/birth timestamps.

Save `fast-b` bytes, mutate one `fast-a` DAT with `write_bytes`, and assert all `fast-b` bytes remain unchanged. Assert no path whose name contains `template` exists under the witness root. Restore/rebuild any mutated fixture before later assertions.

Attempt the duplicate profile:

```python
    before = _inventory(fast_recipient)
    with pytest.raises(FileExistsError):
        seed_profile(
            tmp_path / "fast-a",
            initial_dat_publish=setup_fixtures._publish_fresh_file,
        )
    assert _inventory(fast_recipient) == before
```

Expected: ordinary, writable, single-link files; no aliases or shared mutations; no template; duplicate directory creation refused with original bytes intact.

- [ ] **Step 7: Execute every direct publisher contract inside the same witness**

Use a small inner function that installs a fresh `_OSProxy` on `setup_fixtures.os`, calls the helper once, and returns proxy/path. Patch `Path.exists`, `Path.stat`, `Path.lstat`, `Path.is_file`, `Path.is_dir`, and `Path.is_symlink` to a failing function only around direct helper success/existing-file calls; restore through `monkeypatch.context()` before ordinary filesystem assertions. This catches `Path` preflights, while `_PathProxy` and proxy `stat/lstat/access` catch module-level preflights.

Execute these cases with precise messages and no parametrization:

1. Success: one open, exact flags/mode, payload exact, one close, no fsync.
2. Existing destination: `FileExistsError`, one exact open attempt, bytes unchanged.
3. Partial writes: `write_steps=(2, 1)` and payload `b"abcdef"`; complete bytes present before return.
4. Zero progress: `write_steps=(2, 0)`; raises `OSError` matching `no progress`, descriptor cleanup attempted, destination absent.
5. Mid-write sentinel: `write_steps=(2, sentinel)`; `caught.value is sentinel`, close attempted, destination absent.
6. Close sentinel: `close_error=sentinel`; `caught.value is sentinel`, cleanup retries close, destination absent.

Use a loop over named failure cases inside the test, with assertion messages containing the case name, so these branches do not become additional pytest identities.

- [ ] **Step 8: Run focused GREEN and unchanged default callers**

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures \
  tests/test_ui_setup_schema.py::test_seed_profile_exercises_real_discovery_and_preserves_local_bytes \
  tests/test_ui_setup_schema.py::test_source_seed_has_distinct_documents_ids_and_local_preferences \
  tests/test_ui_setup_schema.py::test_lossless_transport_keeps_real_revision_and_publication_guards \
  tests/test_ui_setup_schema.py::test_lossless_transport_does_not_bypass_verification_before_publish -q
```

Expected: five passed. The four unchanged schema tests prove ordinary calls still use the atomic default.

Collect controller IDs now and compare with Task 1. Expected: 189 IDs; the baseline 188 are the exact prefix; the comprehensive witness is the only suffix; exactly the original 136 IDs use fixture `setup`.

- [ ] **Step 9: Qualify exact temporary mutants independently**

For every row, run the witness green first, apply one match-once mutant with Block B, rerun only the comprehensive witness, require the named assertion, restore, and require empty diffs.

| Mutant | Exact temporary edit | Intended failure |
|---|---|---|
| Remove `O_EXCL` | `os.O_CREAT | os.O_EXCL | os.O_WRONLY` → `os.O_CREAT | os.O_WRONLY` | proxy's exact flag assertion before real open |
| Check-then-open/nonexclusive | insert `if path.exists(): raise FileExistsError(path)` and remove `O_EXCL` | patched `Path.exists` preflight assertion; no open/overwrite evidence substitutes |
| Direct helper fsync | insert `os.fsync(descriptor)` after the write loop and before close | direct `setup_fixtures.os` fsync channel changes from zero; atomic channel remains zero |
| Atomic delegation | replace helper body with `codec.atomicio.write_bytes_atomic(path, data)` | `wingman.atomicio.os` fsync channel changes from zero; direct channel remains zero |
| Extra byte | `remaining = memoryview(data)` → `remaining = memoryview(data + b" ")` | exact file-byte/content-revision parity or direct payload assertion |
| Mapping order | after `account, character = documents(case)`, reverse `bytes:tabsettings_new` only when `initial_dat_publish is not None` | unsorted JSON/order assertion; broad controller failure does not qualify |
| Line endings | before preference writes, convert recipient CRLF to LF only when `initial_dat_publish is not None` | exact recipient YAML/INI byte assertion |
| Hardlink template | temporarily cache the first destination per exact data payload and `os.link` it for the second fast fixture | `st_nlink`, `samefile`, mutation isolation, or no-template assertion |

The hardlink mutant may add a temporary module dictionary immediately above the helper:

```python
_FRESH_FILE_TEMPLATES = {}
```

and use the original helper for the first payload, then `os.link(template, path)` for repeats. It must be restored completely, including the temporary dictionary.

Expected: each red run fails at the intended assertion and no mutation survives. A codec decode error, collection error, cleanup masking, or unrelated later failure is not qualifying evidence.

- [ ] **Step 10: Update results, review, and commit Task 2**

Record parity, source/recipient distinctions, metadata/isolation, all direct contracts, exact fsync/open counts, every mutation result and restoration hash, 189-ID interim collection, unchanged 136 fixture users, and default-caller evidence.

```bash
git diff --check
git diff --exit-code -- wingman tests/test_ui_setup_schema.py \
  tests/test_ui_setup_profile.py tests/test_ui_setup_integration.py \
  tests/fixtures/ui_setup_page.cjs
git add tests/setup_fixtures.py tests/test_ui_setup_controller.py \
  docs/ci-setup-controller-fixture-construction-results.md
git commit -m "test: qualify fresh setup fixture publisher"
```

**Implementer report:** Commit SHA; exact helper/signature; 189-ID and 136-user evidence; direct open flags/mode/count; 4-vs-0 construction fsyncs; parity/isolation/failure results; mutation ledger; restoration proof; changed paths; concerns.

**Fresh reviewer gate:** Review helper cleanup line-by-line, prove no preflight or shared backing, re-run the witness and every mutant, inspect exact failure locations, confirm default calls omit `publish`, compare 188-prefix/one-suffix identities, and approve before Task 3.

**Fix loop:** Restore all mutants first. Any helper, parity, direct-contract, mutation, identity, or default-path issue returns to RED/GREEN in this task. Add only the smallest correction in the two authorized test files/results, rerun every affected mutant and unchanged schema checks, commit a fix, and repeat fresh review.

---

### Task 3: Opt Only the Controller Fixture In and Prove Controller-Body Persistence

**Files:**
- Modify: `tests/test_ui_setup_controller.py:13-49` and append the second witness after the Task 2 witness
- Modify: `docs/ci-setup-controller-fixture-construction-results.md`
- Temporarily modify and restore: `wingman/evesettings/setup_profile.py:206-221`
- Verify unchanged: `tests/fixtures/ui_setup_page.cjs:312-329`

**Interfaces:**
- Consumes: Task 2's `_publish_fresh_file`, optional `seed_profile` seam, `_OSProxy`, and existing `setup.__wrapped__`, `review`, `queue_create`, `assert_create_done` helpers.
- Produces: the unchanged fixture signature `setup(tmp_path, monkeypatch)` using the fresh publisher for exactly four DATs, plus exact second suffix witness `test_fast_fixture_construction_preserves_controller_body_atomic_persistence`.

**Independent deliverable:** The actual hotspot is optimized and the representative create flow proves six pre-publication atomic fsync categories plus one post-publication selection fsync.

- [ ] **Step 1: Append the second witness before changing `setup` and verify RED**

Append the exact non-parameterized witness after Task 2's witness. It must call `setup.__wrapped__(tmp_path, monkeypatch)` directly, not request fixture `setup`.

Install separate `setup_fixtures.os` and `atomicio.os` proxies before calling the wrapped fixture. Assert construction expectations:

```python
    controller, source, base = setup.__wrapped__(tmp_path, monkeypatch)
    assert len(direct.open_calls) == 4
    assert direct.fsync_calls == []
    assert atomic.fsync_calls == []
```

Run:

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fast_fixture_construction_preserves_controller_body_atomic_persistence -q
```

Expected before fixture opt-in: FAIL because construction records zero direct opens and four atomic-channel fsyncs.

- [ ] **Step 2: Opt only the controller fixture into the fresh publisher**

Preserve the fixture definition exactly:

```python
@pytest.fixture
def setup(tmp_path, monkeypatch):
```

Change only its two seed calls:

```python
    source = seed_profile(
        tmp_path,
        case="source",
        name="Source",
        initial_dat_publish=setup_fixtures._publish_fresh_file,
    )
    base = seed_profile(
        tmp_path,
        initial_dat_publish=setup_fixtures._publish_fresh_file,
    )
```

Do not add a fixture argument, wrapper fixture, autouse patch, or module-wide publisher substitution.

Rerun the second witness's construction assertions. Expected: four exact direct opens, zero fsync on both channels.

- [ ] **Step 3: Instrument real body persistence through delegating wrappers**

Add `from wingman.evesettings import controller as controller_mod` to the controller test imports. Inside the second witness, capture real functions before patching:

```python
    real_copy_atomic = atomicio.copy_atomic
    real_write_bytes_atomic = atomicio.write_bytes_atomic
    real_write_atomic = atomicio.write_atomic
    real_write_document = codec.write_document
    real_publish_new = profilecopy.publish_new
```

Extend `_OSProxy` in Task 3 with exact category state. Add these fields in `__init__`:

```python
        self.current_category = None
        self.fsync_categories = []
        self.category_events = None
```

Add this method:

```python
    @contextlib.contextmanager
    def category(self, name):
        previous = self.current_category
        self.current_category = name
        try:
            yield
        finally:
            self.current_category = previous
```

Extend `fsync` before delegating:

```python
    def fsync(self, descriptor):
        self.fsync_calls.append(descriptor)
        if self.current_category is not None:
            self.fsync_categories.append(self.current_category)
            if self.category_events is not None:
                self.category_events.append(self.current_category)
        return self._real.fsync(descriptor)
```

After fixture construction, install all body wrappers exactly as follows:

```python
    events = []
    atomic.category_events = events

    def copy_atomic(source_path, target_path, *args, **kwargs):
        category = (
            "stage_dat_copy"
            if Path(target_path).suffix == ".dat"
            else "stage_local_copy"
        )
        with atomic.category(category):
            return real_copy_atomic(source_path, target_path, *args, **kwargs)

    def write_document(path, document, **kwargs):
        target = Path(path)
        if "publish" not in kwargs and target.parent.name.startswith(
            profilecopy.STAGE_PREFIX
        ):

            def publish(rewrite_path, data):
                with atomic.category("rewrite_dat"):
                    return real_write_bytes_atomic(rewrite_path, data)

            kwargs["publish"] = publish
        return real_write_document(target, document, **kwargs)

    def write_atomic(path, text, *args, **kwargs):
        with atomic.category("selection"):
            return real_write_atomic(path, text, *args, **kwargs)

    def publish_new(staged):
        result = real_publish_new(staged)
        events.append("directory_publish")
        return result

    monkeypatch.setattr(atomicio, "copy_atomic", copy_atomic)
    monkeypatch.setattr(codec, "write_document", write_document)
    monkeypatch.setattr(atomicio, "write_atomic", write_atomic)
    monkeypatch.setattr(profilecopy, "publish_new", publish_new)
```

The `write_document` wrapper explicitly handles the production codec's definition-time publisher default instead of assuming that monkeypatching `atomicio.write_bytes_atomic` changes the stored default. Every wrapper delegates to the real operation; no write is suppressed or replaced.

- [ ] **Step 4: Phase-separate construction and body, run real review/create, and assert exact seven fsyncs**

After the wrapped fixture returns, assert and store construction evidence, then clear direct/atomic counters and event lists. Patch `wingman.evesettings.controller.time.time` to `lambda: 1000.0` so expected rewritten DAT bytes are deterministic.

Compute expected account/character documents from the original recipient snapshots using the real parser and adapter before the create worker runs:

```python
    parsed = setup_sharing.parse_text(setup_sharing.export_text(wire()))
    expected_account, expected_character = setup_documents.apply_setup(
        codec.read_document(base.account_path),
        codec.read_document(base.character_path),
        parsed,
        keep_ship_labels=False,
        now=1000.0,
    )

    def expected_lossless(document):
        envelope = {"had_crc": document.had_crc, "doc": document.doc}
        return b"\x7d" + json.dumps(envelope, ensure_ascii=False).encode("utf-8")
```

Patch the controller module's clock explicitly:

```python
    monkeypatch.setattr(controller_mod.time, "time", lambda: 1000.0)
```

Run the real operation:

```python
    offer, queued = queue_create(controller, base)
    queued.run_next()
    done = assert_create_done(controller, offer, published=True)
```

Assert:

```python
    counts = Counter(atomic.fsync_categories)
    assert counts == Counter({
        "stage_dat_copy": 2,
        "stage_local_copy": 2,
        "rewrite_dat": 2,
        "selection": 1,
    })
    assert len(atomic.fsync_categories) == 7
    publish_index = events.index("directory_publish")
    assert events[:publish_index].count("stage_dat_copy") == 2
    assert events[:publish_index].count("stage_local_copy") == 2
    assert events[:publish_index].count("rewrite_dat") == 2
    assert events[publish_index + 1 :] == ["selection"]
```

Then assert exact final bytes:

```python
    destination = offer.plan.destination
    assert {path.name for path in destination.iterdir()} == {
        base.account_path.name,
        base.character_path.name,
        "core_public__.yaml",
        "prefs.ini",
    }
    assert (destination / base.account_path.name).read_bytes() == expected_lossless(
        expected_account
    )
    assert (destination / base.character_path.name).read_bytes() == expected_lossless(
        expected_character
    )
    assert (destination / "core_public__.yaml").read_bytes() == (
        b"# synthetic recipient local preferences\r\nuiScale: 1.25\r\n"
    )
    assert (destination / "prefs.ini").read_bytes() == (
        b"; synthetic recipient local preferences\r\nmonitor=2\r\n"
    )
    assert controller._settings["eve_settings"]["profile"] == str(destination)
```

Also assert:

- construction counters remain separately stored at four opens/zero fsyncs;
- `done["selection_persisted"] is True`;
- destination inventory is exactly account DAT, character DAT, YAML, and INI;
- destination preference bytes equal recipient CRLF bytes;
- destination DAT bytes equal `expected_lossless()` for the two expected documents;
- `profilecopy.publish_new()` delegated and the hidden stage no longer exists;
- settings selection names the created destination.

Expected: operation completes and exact body count is seven: six categorized atomic fsyncs before directory publication and one selection fsync after publication.

- [ ] **Step 5: Run existing controller failure/race gates and the three direct Node scenarios**

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_create_codec_failure_never_publishes_partial_profile \
  tests/test_ui_setup_controller.py::test_create_external_writer_during_staging_or_final_publish_is_not_overwritten \
  tests/test_ui_setup_controller.py::test_create_preserves_boundary_error_codes_and_failure_context \
  tests/test_ui_setup_controller.py::test_create_publication_survives_housekeeping_failures \
  tests/test_ui_setup_controller.py::test_create_revalidates_authority_and_complete_base \
  tests/test_ui_setup_controller.py::test_create_does_not_trust_authority_from_before_slow_closed_probe -q
uv run --no-sync python -m pytest \
  'tests/test_ui_setup_page.py::test_setup_page_runtime[eve-unknown]' \
  'tests/test_ui_setup_page.py::test_setup_page_runtime[malformed-text]' \
  'tests/test_ui_setup_page.py::test_setup_page_runtime[stale-manifest]' -q
```

Expected: all selected controller cases pass; all three Node scenarios pass through the unchanged direct `setup.__wrapped__(Path(temp), patch)` boundary.

- [ ] **Step 6: Qualify independent construction and body mutants**

Re-run Task 2's direct-fsync and atomic-delegation mutants against the comprehensive witness after fixture opt-in; require the same independent channel failures and exact restoration.

Then qualify the body mutant with Block B against `wingman/evesettings/setup_profile.py`. Replace only the staged account rewrite call:

```python
        written_account_revision = codec.write_document(
            staged_account_path,
            updated_account,
            backup=lambda _path: None,
            expected_content_revision=account_revision,
        )
```

with:

```python
        written_account_revision = codec.write_document(
            staged_account_path,
            updated_account,
            backup=lambda _path: None,
            publish=lambda path, data: Path(path).write_bytes(data),
            expected_content_revision=account_revision,
        )
```

Run only the second witness. Required result:

- create operation and final directory publication complete;
- rewritten DAT atomic category changes from `2` to `1`;
- total categorized body fsyncs change from `7` to `6`;
- the exact `Counter` assertion fails after completion;
- no `FileExistsError`, codec verification failure, revision failure, or publication refusal qualifies.

Restore `setup_profile.py` and require `git diff --exit-code -- wingman/evesettings/setup_profile.py`.

- [ ] **Step 7: Verify exact 190-ID endpoint and fixture-user count**

Run Block C.

Expected: 190 IDs, baseline 188 exact prefix, exact two-name suffix in order, 136 structural setup users unchanged, and 16,607 projected complete identities.

- [ ] **Step 8: Update results, review, and commit Task 3**

Record actual construction/body counters, exact category/order events, final-byte assertions, Node direct-call evidence, body-mutant completion/count failure, exact 190 collection and hashes, 136 fixture users, and restoration proof.

```bash
git diff --check
git diff --exit-code -- wingman tests/fixtures/ui_setup_page.cjs \
  tests/test_ui_setup_page.py
git add tests/test_ui_setup_controller.py \
  docs/ci-setup-controller-fixture-construction-results.md
git commit -m "test: optimize setup controller fixture construction"
```

**Implementer report:** Commit SHA; exact fixture call changes and unchanged signature; construction counts; seven body categories/order; complete bytes and operation result; Node three-scenario result; 190/136 identity evidence; independent mutant results; restoration; changed paths; concerns.

**Fresh reviewer gate:** Independently inspect fixture scope, run the second witness, verify every wrapper delegates, check definition-time codec default handling, reproduce 7→6 body mutant after successful publication, run the Node scenarios, and approve the Task 3 commit.

**Fix loop:** Any construction leak, body count/category/order error, Node break, extra fixture user, identity drift, or mutant masking returns to this task. Restore production first, apply the smallest test-only correction, rerun both witnesses and affected controller/Node gates, commit a fix, and repeat fresh review.

---

### Task 4: Prove the Complete Local Endpoint and Record Final Local Evidence

**Files:**
- Modify: `docs/ci-setup-controller-fixture-construction-results.md`
- Verify only: all repository paths

**Interfaces:**
- Consumes: Tasks 1–3 baseline files, two witnesses, mutation ledger, exact 190 collection, and unchanged default callers.
- Produces: actual 190-controller and 16,607-complete inventories/hashes, full local pass/skip evidence, all setup/native/codec/profilecopy/atomicio/Node gates, exact scope, and clean mutation restoration.

**Independent deliverable:** A complete locally reviewable endpoint with no publication or hosted claim.

- [ ] **Step 1: Build and install the required release codec**

```bash
cd /mnt/c/dev/flygd-wingman/.worktrees/ci-windows-hotspot-audit
cargo build --locked --release \
  --manifest-path packaging/settings-codec/Cargo.toml \
  --target-dir packaging/settings-codec/target
uv run --no-sync python -c "import os,pathlib,shutil; from wingman.evesettings import codec; name='wingman-settings-codec'+('.exe' if os.name=='nt' else ''); source=pathlib.Path('packaging/settings-codec/target/release')/name; target=pathlib.Path('packaging/bin')/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target); assert codec.codec_available()"
node --version
```

Expected: codec built/installed and `codec.codec_available()` true; Node available.

- [ ] **Step 2: Re-run both focused witnesses and exact identity audit**

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py::test_fresh_initial_dat_publisher_preserves_fixture_parity_isolation_and_failures \
  tests/test_ui_setup_controller.py::test_fast_fixture_construction_preserves_controller_body_atomic_persistence -q
uv run --no-sync python /tmp/setup_fixture_endpoint_audit.py
```

Expected: two passed; exact 188-prefix/two-suffix order; 190 unique controller IDs; 136 structural setup users; 16,607 unique complete IDs; exactly two additions and zero removals.

- [ ] **Step 3: Run the complete setup/controller/default/native gate**

```bash
uv run --no-sync python -m pytest \
  tests/test_ui_setup_controller.py \
  tests/test_ui_setup_schema.py \
  tests/test_ui_setup_profile.py \
  tests/test_ui_setup_integration.py \
  tests/test_evesettings_codec.py \
  tests/test_evesettings_profilecopy.py \
  tests/test_atomicio.py -q -rs --durations=50 \
  --junitxml=/tmp/wingman-setup-fixture-focused.xml
```

Expected: all selected tests pass; zero skip caused by missing Node/codec; native setup integration and native codec rows execute; controller file has 190 passes and zero skips.

- [ ] **Step 4: Run the executable setup-page boundary**

```bash
uv run --no-sync python -m pytest \
  'tests/test_ui_setup_page.py::test_setup_page_runtime[eve-unknown]' \
  'tests/test_ui_setup_page.py::test_setup_page_runtime[malformed-text]' \
  'tests/test_ui_setup_page.py::test_setup_page_runtime[stale-manifest]' \
  tests/test_ui_setup_page.py::test_setup_page_worker_protocol_reuses_process_and_correlates_unknown_scenario \
  tests/test_ui_setup_page.py::test_setup_page_worker_isolation_sentinel -q
```

Expected: five passed; direct wrapped-fixture invocation and worker reuse/isolation remain executable.

- [ ] **Step 5: Run complete pytest and audit exact counts/skips**

```bash
uv run --no-sync python -m pytest tests/ -q -rs --durations=50 \
  --junitxml=/tmp/wingman-setup-fixture-full.xml
```

Expected projection for the unchanged Linux environment: 16,593 passed plus 14 intentional skips = 16,607 identities. Parse the actual JUnit rather than substituting the projection. Reject any failure/error, Node skip, settings-codec skip, controller skip, new platform skip, or identity beyond the exact two witnesses.

- [ ] **Step 6: Run independent Cargo, JS, and Ruff gates**

```bash
cargo test --locked --manifest-path packaging/settings-codec/Cargo.toml
node scripts/js_smoke.js
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
git diff --check
```

Expected: Cargo passes; JS smoke passes; Ruff check/format pass; diff check is clean.

- [ ] **Step 7: Re-run all temporary mutations and prove final restoration**

Re-run the eight Task 2 mutants, the two independent fsync-channel mutants, and the Task 3 direct body writer mutant against the final endpoint. Every red run must fail at its intended assertion and every restore must return the target's original SHA-256. Then run both witnesses green again.

Audit residue:

```bash
git diff --exit-code -- wingman .github tests/fixtures \
  tests/test_ui_setup_schema.py tests/test_ui_setup_profile.py \
  tests/test_ui_setup_integration.py tests/test_evesettings_codec.py \
  tests/test_evesettings_profilecopy.py tests/test_atomicio.py \
  pyproject.toml uv.lock packaging
grep -RInE 'MUTATION|Fresh fixture write made no progress.*MUTATION|_FRESH_FILE_TEMPLATES' \
  tests/setup_fixtures.py tests/test_ui_setup_controller.py || true
```

Expected: protected-path diff empty; no mutant dictionary/comment/debug residue.

- [ ] **Step 8: Audit exact scope and arithmetic**

Run Block C again and additionally:

```bash
python - <<'PY'
import subprocess
allowed = {
 'docs/ci-setup-controller-fixture-construction-results.md',
 'docs/superpowers/plans/2026-09-24-setup-controller-fixture-construction.md',
 'docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md',
 'tests/setup_fixtures.py',
 'tests/test_ui_setup_controller.py',
}
changed = set(subprocess.check_output(
 ['git','diff','--name-only','c23788e3..HEAD'], text=True).splitlines())
assert changed == allowed, {'missing': sorted(allowed-changed), 'unexpected': sorted(changed-allowed)}
assert 136 * 2 * 2 == 544
assert 188 + 2 == 190
assert 16605 + 2 == 16607
print('\n'.join(sorted(changed)))
PY
```

Expected: exact five-path scope and arithmetic.

- [ ] **Step 9: Complete local results and commit Task 4**

Record actual inventory hashes, exact two-ID addition, zero removals/renames/reorders, 136 unchanged fixture users, focused/full counts, all 14 normalized Linux skips, controller zero skips, native/Node/Cargo/JS/Ruff results, full mutation restoration, exact scope, and claim discipline.

```bash
git add docs/ci-setup-controller-fixture-construction-results.md
git commit -m "docs: record setup fixture construction verification"
git status --short --branch
```

Expected: clean branch after a documentation-only Task 4 commit.

**Implementer report:** Commit SHA; actual 190/16,607 hashes and inventories; two additions/zero removals; 136 structural users; focused/full pass/skip counts; exact commands; native/Node/Cargo/JS/Ruff results; mutation restoration; scope; remaining risks. Do not state a speedup.

**Fresh reviewer gate:** Re-run Block C, inspect JUnit/skip tuples, run both witnesses and a representative native/Node gate, verify arithmetic and five-path scope, inspect mutation restore records, and approve Task 4.

**Fix loop:** Route failures to the owning task: helper/parity/direct contracts to Task 2, fixture/body/Node to Task 3, environment/count/scope/results to Task 4. Apply the smallest authorized correction, rerun all affected and endpoint checks, commit a fix, and repeat fresh review.

---

### Task 5: Polish, Whole Review, Publication Stop, and Hosted Windows/Ubuntu Comparison

**Files:**
- Modify: `docs/ci-setup-controller-fixture-construction-results.md`
- Review: approved spec, this plan, complete `c23788e3..HEAD` diff, local JUnit/inventories, and PR #287 comparator artifacts
- Do not push until explicit maintainer authorization

**Interfaces:**
- Consumes: clean locally verified Task 4 endpoint.
- Produces: polished/reviewed branch, reviewer-facing change explanation, explicit publication checkpoint, and—only after authorization—hosted provenance/artifact comparison proving the exact two-ID addition and structural 544-fsync reduction claim.

**Independent deliverable:** Review and publication readiness are complete before any remote mutation; hosted evidence is a separate authorized phase.

- [ ] **Step 1: Run `polish-core --fix` over the whole tranche**

Load `polish-core` and run its fix workflow against `c23788e3..HEAD`. Inspect every edit. Reject any edit outside the five-path allowlist or any weakening of exact assertions. Rerun affected tests, Block C, Ruff, and `git diff --check`; commit only high-confidence corrections in a separate fix commit.

Expected: no unreviewed polish edit remains and executable identities remain 190/16,607 with exact suffix.

- [ ] **Step 2: Obtain an independent whole-branch review**

A fresh reviewer examines:

- spec-to-plan-to-results coverage;
- helper exclusivity and original-exception cleanup;
- no-preflight and exact flag/mode evidence;
- atomic/fast parity, order/types/CRC/revisions/discovery/manifests;
- isolation, metadata, links, duplicate behavior;
- separate direct/atomic fsync channels;
- exact seven body categories and publication/selection order;
- every mutation's intended assertion and restoration;
- identity/fixture-use/skip/scope/claim discipline;
- unchanged Node wrapped-fixture signature.

Resolve every Critical or Important finding, rerun affected tests and final gates, and obtain fresh approval after each fix wave.

- [ ] **Step 3: Run fresh final local verification on the reviewed executable head**

At minimum rerun:

- both focused witnesses;
- Block C;
- complete controller/setup/default/native gate;
- three direct Node scenarios;
- full pytest with skip audit;
- Cargo, JS smoke, Ruff check/format;
- scope/protected-path/diff checks.

Record the exact reviewed executable head SHA in the results document.

- [ ] **Step 4: Run `change-explainer`**

Load `change-explainer` and produce the reviewer-facing summary from the final diff, tests, results, and verification. It must explain the four fresh DAT publications, why default callers remain atomic, how original exceptions survive cleanup, how controller-body atomic work is phase-separated, the exact two test IDs, the mutation evidence, actual verification, reviewer focus, and remaining risks. It must make only the structural 544-fsync claim.

- [ ] **Step 5: Stop for explicit publication authorization**

Present:

- reviewed head SHA and clean status;
- exact 190 controller and 16,607 complete inventories/hashes;
- exact two-ID suffix and zero removals;
- 136 unchanged setup users;
- local pass/skip/gate results;
- whole-review outcome;
- proposed PR title `Optimize setup controller fixture construction`;
- proposed body stating four exclusive fresh DAT publications per setup fixture, preserved codec/body persistence, exact identity delta, and no speedup claim.

Do not push, open a PR, rerun GitHub workflows, or call a GitHub mutation API before explicit authorization.

- [ ] **Step 6: After authorization, collect exact hosted provenance and artifacts**

Resolve the PR and successful run from the reviewed branch head. Record branch head, base, synthetic merge, workflow run, checks/Ubuntu/Windows job IDs, artifact IDs/digests, checkout refs/subjects, Test-step seconds, and job seconds. Require merge parents `[synthetic, base, head]` in that order.

Download successful Ubuntu/Windows `pytest-evidence-*` artifacts into new roots, never overwrite `/tmp/wingman-stage3-{ubuntu,windows}`.

- [ ] **Step 7: Enforce the synthetic-merge full-diff allowlist**

Compare PR #287 synthetic merge `ab2028f55f080e6067d7cc62002451f96171fa68` to the new synthetic merge. The exact expected six-path union is:

```text
docs/ci-generated-verifier-alerts-consolidation-results.md
docs/ci-setup-controller-fixture-construction-results.md
docs/superpowers/plans/2026-09-24-setup-controller-fixture-construction.md
docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md
tests/setup_fixtures.py
tests/test_ui_setup_controller.py
```

The first path is the known post-PR-#287 merge delta from `ab2028...` to `c23788e3`; the remaining five are this tranche. Run:

```python
expected = {
    'docs/ci-generated-verifier-alerts-consolidation-results.md',
    'docs/ci-setup-controller-fixture-construction-results.md',
    'docs/superpowers/plans/2026-09-24-setup-controller-fixture-construction.md',
    'docs/superpowers/specs/2026-09-24-setup-controller-fixture-construction-design.md',
    'tests/setup_fixtures.py',
    'tests/test_ui_setup_controller.py',
}
full = changed('ab2028f55f080e6067d7cc62002451f96171fa68', new_synthetic)
assert full == expected, {'missing': sorted(expected-full), 'unexpected': sorted(full-expected)}
assert not any(path.startswith(('.github/', 'wingman/', 'scripts/', 'tests/fixtures/', 'packaging/')) for path in full)
assert not (full & {'pyproject.toml', 'uv.lock'})
assert not {path for path in full if path.startswith('tests/') and path not in {
    'tests/setup_fixtures.py', 'tests/test_ui_setup_controller.py'}}
```

Any unexpected base movement/path makes comparison inconclusive; do not hand-pick only executable files.

- [ ] **Step 8: Parse hosted artifacts against the PR #287 baseline**

The hosted parser must require, on both platforms:

- exact 16,607 unique complete identities;
- Ubuntu/Windows complete identity sets equal;
- PR #287's complete 16,605-ID set is a subset;
- after-minus-baseline is exactly the two approved witness IDs in the documented order;
- baseline-minus-after is empty;
- exact 190 controller list whose first 188 equal Task 1 and whose suffix equals the two names;
- zero controller skips;
- zero failures/errors;
- each platform's normalized skip tuples equal its PR #287 platform baseline exactly: Ubuntu 14, Windows 67;
- observed pass counts 16,593/14 on Ubuntu and 16,540/67 on Windows if identities/skips match;
- JUnit/timing JSON agreement for case counts and per-file sums;
- controller testcase sum, the retained 136 setup-user sum where node timing permits, other-controller sum, and slowest retained controller identities;
- Test-step/job durations as observations only.

Write actual hosted controller/full hashes from newline-terminated lists. Compare local and hosted identities byte-for-set and controller order.

- [ ] **Step 9: Record hosted evidence with claim discipline**

Record provenance, artifact identity, synthetic diff, identity/skip comparison, exact two additions/zero removals, controller order, testcase sums, slowest retained IDs, and Test/job observations. State explicitly:

- verified structural reduction: 136 existing setup users × 4 initial DATs = 544 fixture-only fsync calls removed;
- two new witnesses add qualification work but do not consume fixture `setup` and do not change 544;
- one hosted run supports no speedup, regression attribution, runner-efficiency, critical-path, or wall-clock conclusion.

Any extra identity, removed/reordered baseline ID, platform identity divergence, skip change, availability skip, failure/error, protected path, or unexplained synthetic diff is a stop.

- [ ] **Step 10: Commit hosted evidence and verify the evidence head**

After hosted comparison succeeds, commit only the results document:

```bash
git add docs/ci-setup-controller-fixture-construction-results.md
git commit -m "docs: record hosted setup fixture construction evidence"
```

Push this evidence commit only if separately authorized, then wait for required checks on that exact documentation head. Record those checks separately from executable timing evidence.

**Implementer report:** Polish edits; whole-review verdict/fixes; reviewed and evidence SHAs; exact hosted run/jobs/artifacts/provenance; six-path synthetic diff; 16,607/190 identities and hashes; two additions/zero removals/reorders; 14/67 skips; testcase/Test/job observations; structural 544 claim; evidence-head checks; unresolved concerns.

**Fresh reviewer gate:** Independently verify merge parents/logs, six-path synthetic diff, artifact IDs/digests, complete identity and skip sets, controller prefix/suffix, timing-json agreement, scope, and no speedup wording before accepting hosted evidence.

**Fix loop:** Local review findings return to the owning task. Hosted provenance/artifact incomparability yields `INCONCLUSIVE` and a repeat run, not inference. Contract failure yields `STOP / repair`; apply no workflow, selector, dependency, production, or broader fixture change under this plan.

---

## Required Plan Self-Review

- **Spec coverage:** Task 1 owns exact baseline/provenance/timing/skips/results ledger; Task 2 owns helper/default seam/parity/isolation/direct failures and all helper mutants; Task 3 owns sole fixture opt-in, unchanged signature, body categories/order and direct body mutant; Task 4 owns complete local endpoint and scope; Task 5 owns polish/review/change explanation/publication stop/hosted comparison.
- **Names and ordering:** The exact two witness names are defined once in Global Constraints, Block C, Tasks 2–3, and hosted acceptance; Task 2 appends the first, Task 3 appends the second, preserving the 188 prefix.
- **Counts and arithmetic:** `136 × 4 = 544`, `188 + 2 = 190`, `16,605 + 2 = 16,607`, Ubuntu projection `16,593 + 14`, Windows projection `16,540 + 67`.
- **Signature consistency:** `_publish_fresh_file(path: Path, data: bytes) -> None`; `seed_profile(..., initial_dat_publish=None)`; fixture remains `setup(tmp_path, monkeypatch)`; both witnesses use `(tmp_path, monkeypatch)` and do not request `setup`.
- **OS proxy safety:** both module bindings are replaced separately; no attribute on the shared real `os` module is mutated; exact flags include platform `O_BINARY`; exact mode is `0o600`; real operations delegate.
- **Original exception implementability:** helper retries/suppresses cleanup while a bare `raise` preserves the write/close sentinel object; existing-file open failure occurs before cleanup and cannot unlink the predecessor.
- **Mutation exactness:** Block B requires one exact source match and byte restoration; O_EXCL, check-then-open, direct fsync, atomic delegation, bytes, order, line endings, hardlink, and body direct-write mutants all name their intended assertions.
- **Identity hashes:** scripts compute actual hashes; the plan contains no projected node hash target.
- **Hosted comparison:** comparator synthetic/full diff uses the exact six-path allowlist and platform-local skip comparison; failed/incomparable evidence cannot be normalized away.
- **No placeholders or scope expansion:** every task contains exact files, interfaces, commands, code, expected outcomes, commit, implementer report, reviewer gate, and fix loop; no production or workflow implementation is authorized.
